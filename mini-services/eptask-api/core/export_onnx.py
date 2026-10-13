import json
import os
import time
import numpy as np
import torch
import torch.nn as nn


class SingleGroupActor(nn.Module):
    """Ordinary, un-grouped actor -- one vehicle-count policy, no group axis."""

    def __init__(self, state_dim, n_tasks=10, n_offload=4, n_prio=10, hidden=64):
        super().__init__()
        self.K, self.A, self.P = n_tasks, n_offload, n_prio
        self.a1 = nn.Linear(state_dim, hidden)
        self.a2 = nn.Linear(hidden, hidden)
        self.h_off = nn.Linear(hidden, n_tasks * n_offload)
        self.h_pri = nn.Linear(hidden, n_tasks * n_prio)

    def forward(self, s):                      # s: (B, state_dim)
        x = torch.tanh(self.a2(torch.tanh(self.a1(s))))
        off = self.h_off(x).view(-1, self.K, self.A)
        pri = self.h_pri(x).view(-1, self.K, self.P)
        return off, pri


def slice_group(grouped_net, g):
    """Copy group g's weights out of a trained GroupedActorCritic into a
    plain SingleGroupActor. Exact -- a transpose and a group-index."""
    m = SingleGroupActor(grouped_net.a1.w.shape[1], grouped_net.K,
                         grouped_net.A, grouped_net.P,
                         hidden=grouped_net.a1.w.shape[2])
    with torch.no_grad():
        m.a1.weight.copy_(grouped_net.a1.w[g].T)
        m.a1.bias.copy_(grouped_net.a1.b[g, 0])
        m.a2.weight.copy_(grouped_net.a2.w[g].T)
        m.a2.bias.copy_(grouped_net.a2.b[g, 0])
        m.h_off.weight.copy_(grouped_net.h_off.w[g].T)
        m.h_off.bias.copy_(grouped_net.h_off.b[g, 0])
        m.h_pri.weight.copy_(grouped_net.h_pri.w[g].T)
        m.h_pri.bias.copy_(grouped_net.h_pri.b[g, 0])
    return m.eval()


def export_group(checkpoint_path, group, out_path, opset=17):
    """Load a checkpoint, slice out `group` (an index OR the actual vehicle
    count, e.g. 30), write an ONNX file to out_path."""
    from nets import GroupedActorCritic

    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    counts = ckpt["vehicle_counts"]
    g = counts.index(group) if group in counts else int(group)

    net = GroupedActorCritic(len(counts), ckpt["state_dim"], ckpt["n_tasks"],
                             ckpt["n_offload"], ckpt["n_prio"])
    net.load_state_dict(ckpt["state_dict"])
    net.eval()

    single = slice_group(net, g)
    dummy = torch.randn(1, ckpt["state_dim"], dtype=torch.float32)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    exporter = _onnx_export(single, ckpt["state_dim"], out_path, opset)
    info = dict(vehicle_count=counts[g], group=g, episode=ckpt.get("episode"),
                n_episodes=ckpt.get("n_episodes"), state_dim=ckpt["state_dim"],
                out_path=out_path, size_bytes=os.path.getsize(out_path),
                exporter=exporter, cfg_kw=ckpt.get("cfg_kw", {}),
                created=time.strftime("%Y-%m-%d %H:%M:%S"))
    # V7.1 sidecar: what a consumer (the demo, an agent) needs to rebuild the
    # matching environment -- state encoding and switches.
    with open(out_path + ".json", "w") as fh:
        json.dump(info, fh, indent=1)
    return info


def _onnx_export(model, state_dim, out_path, opset):
    """Legacy TorchScript exporter first (what v5/v6 used); newer torch
    releases may drop it, so fall back to the dynamo exporter (batch of 2:
    torch.export specialises a size-1 dimension)."""
    names = dict(input_names=["state"], output_names=["offload_logits", "priority_logits"])
    try:
        torch.onnx.export(model, torch.randn(1, state_dim), out_path,
                          dynamic_axes={"state": {0: "batch"}}, opset_version=opset,
                          dynamo=False, **names)
        return "torchscript"
    except Exception as e1:
        try:
            torch.onnx.export(model, (torch.randn(2, state_dim),), out_path, dynamo=True,
                              dynamic_shapes=({0: torch.export.Dim("batch")},), **names)
            return "dynamo"
        except Exception as e2:
            raise RuntimeError(f"ONNX export failed: legacy={e1!r} dynamo={e2!r}")


def verify(checkpoint_path, group, onnx_path, n_trials=8, atol=1e-4):
    """Checks (1) sliced PyTorch vs original grouped network, (2) exported
    ONNX vs sliced PyTorch. Raises if either mismatches beyond float32
    rounding -- treat a failure as a real bug, never deploy that file."""
    import onnxruntime as ort
    from nets import GroupedActorCritic

    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    counts = ckpt["vehicle_counts"]
    g = counts.index(group) if group in counts else int(group)
    state_dim = ckpt["state_dim"]

    net = GroupedActorCritic(len(counts), state_dim, ckpt["n_tasks"],
                             ckpt["n_offload"], ckpt["n_prio"])
    net.load_state_dict(ckpt["state_dict"]); net.eval()
    single = slice_group(net, g)
    sess = ort.InferenceSession(onnx_path)

    worst_slice, worst_onnx = 0.0, 0.0
    for _ in range(n_trials):
        s = np.random.randn(1, state_dim).astype(np.float32)
        s_grouped = torch.zeros(len(counts), 1, state_dim)
        s_grouped[g, 0] = torch.as_tensor(s[0])
        with torch.no_grad():
            off_full, pri_full, _ = net(s_grouped)
            off_single, pri_single = single(torch.as_tensor(s))
        worst_slice = max(worst_slice,
                          (off_full[g, 0] - off_single[0]).abs().max().item(),
                          (pri_full[g, 0] - pri_single[0]).abs().max().item())
        off_onnx, pri_onnx = sess.run(None, {"state": s})
        worst_onnx = max(worst_onnx,
                         np.abs(off_single.numpy() - off_onnx).max(),
                         np.abs(pri_single.numpy() - pri_onnx).max())

    ok = worst_slice < atol and worst_onnx < atol
    print(f"verify: slice-vs-grouped max diff = {worst_slice:.2e}  (tolerance {atol:.0e})")
    print(f"verify: onnx-vs-pytorch max diff  = {worst_onnx:.2e}  (tolerance {atol:.0e})")
    print("verify:", "PASSED" if ok else "FAILED -- do not deploy this file")
    assert ok, "exported ONNX does not match the trained model"
    return dict(slice_diff=worst_slice, onnx_diff=worst_onnx)
