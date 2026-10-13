import hashlib

path = '/home/z/my-project/workspace/extracted/notebook_raw/v7.1/eptask/contributions.py'
raw = open(path, 'rb').read()
print("md5:", hashlib.md5(raw).hexdigest(), "size:", len(raw))

needle = b'ROLE_NAMES'
i = -1
occ = 0
while True:
    i = raw.find(needle, i + 1)
    if i < 0:
        break
    occ += 1
    print(f"occurrence {occ} @ {i}: {raw[max(0,i-20):i+40]!r}")

print('count of m["role"] bytes:', raw.count(b'm["role"]'))
print("count of m['role'] bytes:", raw.count(b"m['role']"))
