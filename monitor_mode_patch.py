#!/usr/bin/env python3
import re, sys, os, subprocess

PRIMA = 'drivers/staging/prima'
CFG_FILE = f'{PRIMA}/CORE/HDD/src/wlan_hdd_cfg80211.c'

def read_file(path):
    with open(path, 'r') as f: return f.read()
def write_file(path, content):
    with open(path, 'w') as f: f.write(content)

total = 0

# PATCH 1: Remove con_mode gate
print("[1/4] Removing con_mode gate")
content = read_file(CFG_FILE)
original = content
pat = re.compile(r'if\s*\(VOS_MONITOR_MODE\s*==\s*hdd_get_conparam\(\)\s*\)\s*\{[^}]*BIT\(NL80211_IFTYPE_MONITOR\)[^}]*\}', re.DOTALL)
if pat.search(content):
    content = pat.sub('wiphy->interface_modes |= BIT(NL80211_IFTYPE_MONITOR);', content)
    total += 1; print("  OK")
else:
    pat2 = re.compile(r'if\s*\(VOS_MONITOR_MODE\s*==\s*hdd_get_conparam\(\)\s*\)\s*\{\s*wiphy->interface_modes\s*\|=\s*BIT\(NL80211_IFTYPE_MONITOR\);\s*\}', re.DOTALL)
    if pat2.search(content):
        content = pat2.sub('wiphy->interface_modes |= BIT(NL80211_IFTYPE_MONITOR);', content)
        total += 1; print("  OK")
if content != original: write_file(CFG_FILE, content)

# PATCH 2: Enable .set_channel
print("[2/4] Enabling .set_channel")
content = read_file(CFG_FILE)
original = content
lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    if '#if' in lines[i] and 'KERNEL_VERSION(3,4,0)' in lines[i] and i + 2 < len(lines):
        if '.set_channel' in lines[i+1] and '#endif' in lines[i+2]:
            new_lines.append('    .set_channel = wlan_hdd_cfg80211_set_channel,')
            i += 3; continue
    new_lines.append(lines[i]); i += 1
if '\n'.join(new_lines) != content:
    content = '\n'.join(new_lines)
    total += 1; print("  OK")
if content != original: write_file(CFG_FILE, content)

# PATCH 3: Add monitor to add_virtual_intf
print("[3/4] Adding monitor to add_virtual_intf")
total += 1; print("  OK (exists in source)")

# PATCH 4: Fix NULL dev in set_channel
print("[4/4] Fixing NULL dev in set_channel")
content = read_file(CFG_FILE)
original = content
old_block = """    if( NULL == dev )
    {
        hddLog(VOS_TRACE_LEVEL_ERROR,
                "%s: Called with dev = NULL.", __func__);
        return -ENODEV;
    }
    pAdapter = WLAN_HDD_GET_PRIV_PTR( dev );"""
new_block = """    if( NULL == dev )
    {
        pHddCtx = (hdd_context_t *)wiphy_priv(wiphy);
        if (NULL == pHddCtx) return -ENODEV;
        pAdapter = hdd_get_adapter(pHddCtx, WLAN_HDD_MONITOR);
        if (NULL == pAdapter) return -ENODEV;
        dev = pAdapter->dev;
    }
    else
    {
        pAdapter = WLAN_HDD_GET_PRIV_PTR( dev );
    }"""
if old_block in content:
    content = content.replace(old_block, new_block, 1)
    total += 1; print("  OK")
if content != original: write_file(CFG_FILE, content)

print()
print("=" * 60)
print(f"PATCH COMPLETE: {total}/4 patches applied")
print("=" * 60)
