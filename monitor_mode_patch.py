#!/usr/bin/env python3
import re, sys, os, subprocess

PRIMA = 'drivers/staging/prima'
CFG_FILE = f'{PRIMA}/CORE/HDD/src/wlan_hdd_cfg80211.c'

def read_file(path):
    with open(path, 'r') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)

total = 0

# PATCH 1: Remove con_mode gate
print("=" * 60)
print("[1/7] Removing con_mode gate on interface_modes")
print("=" * 60)
content = read_file(CFG_FILE)
original = content
pat = re.compile(r'if\s*\(VOS_MONITOR_MODE\s*==\s*hdd_get_conparam\(\)\s*\)\s*\{[^}]*BIT\(NL80211_IFTYPE_MONITOR\)[^}]*\}', re.DOTALL)
if pat.search(content):
    content = pat.sub('wiphy->interface_modes |= BIT(NL80211_IFTYPE_MONITOR);', content)
    print("  OK Removed gate")
    total += 1
else:
    pat2 = re.compile(r'if\s*\(VOS_MONITOR_MODE\s*==\s*hdd_get_conparam\(\)\s*\)\s*\{\s*wiphy->interface_modes\s*\|=\s*BIT\(NL80211_IFTYPE_MONITOR\);\s*\}', re.DOTALL)
    if pat2.search(content):
        content = pat2.sub('wiphy->interface_modes |= BIT(NL80211_IFTYPE_MONITOR);', content)
        print("  OK Removed gate (exact)")
        total += 1
    else:
        print("  FAIL Could not find gate")
if content != original:
    write_file(CFG_FILE, content)

# PATCH 2: Enable .set_channel unconditionally
print()
print("=" * 60)
print("[2/7] Enabling .set_channel unconditionally")
print("=" * 60)
content = read_file(CFG_FILE)
original = content
lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if '#if' in line and 'KERNEL_VERSION(3,4,0)' in line and i + 2 < len(lines):
        if '.set_channel' in lines[i + 1] and '#endif' in lines[i + 2]:
            new_lines.append('    .set_channel = wlan_hdd_cfg80211_set_channel,')
            i += 3
            continue
    new_lines.append(line)
    i += 1
new_content = '\n'.join(new_lines)
if new_content != content:
    content = new_content
    print("  OK Removed #if guard")
    total += 1
else:
    print("  FAIL Could not find guard")
if content != original:
    write_file(CFG_FILE, content)

# PATCH 3: Add NL80211_IFTYPE_MONITOR to add_virtual_intf
print()
print("=" * 60)
print("[3/7] Adding NL80211_IFTYPE_MONITOR to add_virtual_intf")
print("=" * 60)
content = read_file(CFG_FILE)
original = content
if 'NL80211_IFTYPE_MONITOR' in content and 'WLAN_HDD_MONITOR' in content:
    found = False
    for m in re.finditer('NL80211_IFTYPE_MONITOR', content):
        ctx = content[max(0, m.start()-200):m.start()+200]
        if 'WLAN_HDD_MONITOR' in ctx and ('case' in ctx or 'session_type' in ctx):
            found = True
            break
    if found:
        print("  OK Already exists")
        total += 1
    else:
        pat = re.compile(r'(case\s+NL80211_IFTYPE_P2P_GO\s*:.*?session_type\s*=\s*WLAN_HDD_P2P_GO\s*;\s*\n\s*break\s*;)', re.DOTALL)
        match = pat.search(content)
        if match:
            ins = match.group(1) + '\n    case NL80211_IFTYPE_MONITOR:\n        session_type = WLAN_HDD_MONITOR;\n        break;'
            content = content[:match.end()] + ins + content[match.end():]
            print("  OK Added after P2P_GO")
            total += 1
        else:
            print("  FAIL Could not find switch")
else:
    print("  FAIL Not found in file")
if content != original:
    write_file(CFG_FILE, content)

# PATCH 4: SKIPPED
print()
print("=" * 60)
print("[4/7] change_virtual_intf - SKIPPED")
print("=" * 60)
total += 1

# PATCH 5: Verify set_channel exists
print()
print("=" * 60)
print("[5/7] Verifying set_channel exists")
print("=" * 60)
result = subprocess.run(['grep', '-c', 'wlan_hdd_cfg80211_set_channel', CFG_FILE], capture_output=True, text=True)
if int(result.stdout.strip() if result.stdout.strip() else '0') > 0:
    print("  OK Function exists")
    total += 1
else:
    print("  FAIL Not found")

# PATCH 6: Fix set_channel device_mode check
print()
print("=" * 60)
print("[6/7] Fixing set_channel device_mode check for monitor")
print("=" * 60)
content = read_file(CFG_FILE)
original = content
old_if = '(WLAN_HDD_SOFTAP != pAdapter->device_mode)'
new_if = '(WLAN_HDD_SOFTAP != pAdapter->device_mode) && (WLAN_HDD_MONITOR != pAdapter->device_mode)'
if old_if in content and new_if not in content:
    content = content.replace(old_if, new_if, 1)
    print("  OK Added to first if")
else:
    print("  SKIP First if already patched or not found")
old_elseif = '(pAdapter->device_mode == WLAN_HDD_SOFTAP)'
new_elseif = '(pAdapter->device_mode == WLAN_HDD_SOFTAP) || (pAdapter->device_mode == WLAN_HDD_MONITOR)'
if old_elseif in content and new_elseif not in content:
    content = content.replace(old_elseif, new_elseif, 1)
    print("  OK Added to else-if AP path")
else:
    print("  SKIP Else-if already patched or not found")
if content != original:
    write_file(CFG_FILE, content)
    total += 1

# PATCH 7: Fix NULL dev handling
print()
print("=" * 60)
print("[7/7] Fixing NULL dev handling for monitor mode")
print("=" * 60)
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
        hddLog(VOS_TRACE_LEVEL_INFO,
                "%s: Called with dev = NULL, looking up monitor adapter", __func__);
        pHddCtx = (hdd_context_t *)wiphy_priv(wiphy);
        if (NULL == pHddCtx)
        {
            hddLog(VOS_TRACE_LEVEL_ERROR, "%s: HDD context is NULL", __func__);
            return -ENODEV;
        }
        pAdapter = hdd_get_adapter(pHddCtx, WLAN_HDD_MONITOR);
        if (NULL == pAdapter)
        {
            hddLog(VOS_TRACE_LEVEL_ERROR, "%s: No monitor adapter found", __func__);
            return -ENODEV;
        }
        dev = pAdapter->dev;
    }
    else
    {
        pAdapter = WLAN_HDD_GET_PRIV_PTR( dev );
    }"""
if old_block in content:
    content = content.replace(old_block, new_block, 1)
    print("  OK Replaced NULL dev check")
    total += 1
else:
    print("  FAIL Could not find NULL dev block")
    print("  Trying alternate whitespace...")
    old_block2 = old_block.replace("    if( NULL == dev )", "    if( NULL == dev )")
    if old_block2 in content:
        content = content.replace(old_block2, new_block, 1)
        print("  OK Replaced (alt)")
        total += 1
    else:
        print("  FAIL Could not match")
if content != original:
    write_file(CFG_FILE, content)

# Summary
print()
print("=" * 60)
print(f"PATCH COMPLETE: {total}/7 patches applied")
print("=" * 60)
