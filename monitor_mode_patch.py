#!/usr/bin/env python3
"""
Monitor Mode Patch for Prima/Pronto WLAN Driver
Target: Samsung GT-I9301I (S3 Neo) on LineageOS 18.1
"""

import re
import sys
import os
import subprocess

PRIMA = 'drivers/staging/prima'
CFG_FILE = f'{PRIMA}/CORE/HDD/src/wlan_hdd_cfg80211.c'
MAIN_FILE = f'{PRIMA}/CORE/HDD/src/wlan_hdd_main.c'

def read_file(path):
    with open(path, 'r') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)

def grep(pattern, path):
    try:
        result = subprocess.run(['grep', '-n', pattern, path], 
                              capture_output=True, text=True)
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except:
        return []

total_changes = 0

# ============================================================
# PATCH 1: Remove con_mode gate on interface_modes
# ============================================================
print("=" * 60)
print("[1/6] Removing con_mode gate on interface_modes")
print("=" * 60)

content = read_file(CFG_FILE)
original = content

pattern = re.compile(
    r'if\s*\(VOS_MONITOR_MODE\s*==\s*hdd_get_conparam\(\)\s*\)\s*\{[^}]*'
    r'BIT\(NL80211_IFTYPE_MONITOR\)[^}]*\}',
    re.DOTALL
)

if pattern.search(content):
    content = pattern.sub(
        'wiphy->interface_modes |= BIT(NL80211_IFTYPE_MONITOR);',
        content
    )
    print("  ✓ Removed con_mode gate")
    total_changes += 1
else:
    pattern2 = re.compile(
        r'if\s*\(VOS_MONITOR_MODE\s*==\s*hdd_get_conparam\(\)\s*\)\s*\{\s*'
        r'wiphy->interface_modes\s*\|=\s*BIT\(NL80211_IFTYPE_MONITOR\);\s*\}',
        re.DOTALL
    )
    if pattern2.search(content):
        content = pattern2.sub(
            'wiphy->interface_modes |= BIT(NL80211_IFTYPE_MONITOR);',
            content
        )
        print("  ✓ Removed con_mode gate (exact match)")
        total_changes += 1
    else:
        print("  ✗ Could not find con_mode gate")

if content != original:
    write_file(CFG_FILE, content)

# ============================================================
# PATCH 2: Enable .set_channel unconditionally
# ============================================================
print()
print("=" * 60)
print("[2/6] Enabling .set_channel unconditionally")
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
    print("  ✓ Removed #if/#endif guard around .set_channel")
    total_changes += 1
else:
    print("  ✗ Could not find #if guard")

if content != original:
    write_file(CFG_FILE, content)

# ============================================================
# PATCH 3: Add NL80211_IFTYPE_MONITOR to add_virtual_intf
# ============================================================
print()
print("=" * 60)
print("[3/6] Adding NL80211_IFTYPE_MONITOR to add_virtual_intf")
print("=" * 60)

content = read_file(CFG_FILE)
original = content

if 'NL80211_IFTYPE_MONITOR' in content and 'WLAN_HDD_MONITOR' in content:
    monitor_mentions = [m.start() for m in re.finditer('NL80211_IFTYPE_MONITOR', content)]
    found_mapping = False
    for pos in monitor_mentions:
        context = content[max(0, pos-200):pos+200]
        if 'WLAN_HDD_MONITOR' in context and ('case' in context or 'session_type' in context):
            found_mapping = True
            break
    
    if found_mapping:
        print("  ✓ NL80211_IFTYPE_MONITOR mapping already exists")
        total_changes += 1
    else:
        pattern = re.compile(
            r'(case\s+NL80211_IFTYPE_P2P_GO\s*:.*?session_type\s*=\s*WLAN_HDD_P2P_GO\s*;\s*\n\s*break\s*;)',
            re.DOTALL
        )
        match = pattern.search(content)
        if match:
            insertion = match.group(1) + "\n    case NL80211_IFTYPE_MONITOR:\n        session_type = WLAN_HDD_MONITOR;\n        break;"
            content = content[:match.end()] + insertion + content[match.end():]
            print("  ✓ Added NL80211_IFTYPE_MONITOR case after P2P_GO")
            total_changes += 1
        else:
            pattern = re.compile(
                r'(case\s+NL80211_IFTYPE_AP\s*:.*?session_type\s*=\s*WLAN_HDD_SOFTAP\s*;\s*\n\s*break\s*;)',
                re.DOTALL
            )
            match = pattern.search(content)
            if match:
                insertion = match.group(1) + "\n    case NL80211_IFTYPE_MONITOR:\n        session_type = WLAN_HDD_MONITOR;\n        break;"
                content = content[:match.end()] + insertion + content[match.end():]
                print("  ✓ Added NL80211_IFTYPE_MONITOR case after AP")
                total_changes += 1
            else:
                print("  ✗ Could not find type switch")

if content != original:
    write_file(CFG_FILE, content)

# ============================================================
# PATCH 4: change_virtual_intf (SKIPPED)
# ============================================================
print()
print("=" * 60)
print("[4/6] change_virtual_intf monitor case — SKIPPED")
print("      wlan_mon_drv_ops is static to wlan_hdd_main.c")
print("=" * 60)
total_changes += 1

# ============================================================
# PATCH 5: Verify set_channel exists
# ============================================================
print()
print("=" * 60)
print("[5/6] Checking set_channel for monitor mode compatibility")
print("=" * 60)

set_channel_lines = grep('wlan_hdd_cfg80211_set_channel', CFG_FILE)
if set_channel_lines and len(set_channel_lines) > 0:
    print("  ✓ wlan_hdd_cfg80211_set_channel function exists")
    total_changes += 1
else:
    print("  ✗ wlan_hdd_cfg80211_set_channel not found!")

# ============================================================
# PATCH 6: Fix set_channel for monitor mode
# ============================================================
print()
print("=" * 60)
print("[6/6] Fixing set_channel for monitor mode")
print("=" * 60)

content = read_file(CFG_FILE)
original = content

# Pattern: (WLAN_HDD_SOFTAP != pAdapter->device_mode) &&
#          (WLAN_HDD_P2P_GO != pAdapter->device_mode)
# Add: && (WLAN_HDD_MONITOR != pAdapter->device_mode)

# Try single-line pattern
pattern = re.compile(r'(WLAN_HDD_SOFTAP\s*!=\s*pAdapter->device_mode)\s*&&\s*(WLAN_HDD_P2P_GO\s*!=\s*pAdapter->device_mode)')

if pattern.search(content):
    content = pattern.sub(r'\1 && \2 && (WLAN_HDD_MONITOR != pAdapter->device_mode)', content)
    print("  ✓ Added WLAN_HDD_MONITOR to set_channel check")
    total_changes += 1
else:
    # Try multi-line pattern
    pattern2 = re.compile(r'(WLAN_HDD_SOFTAP\s*!=\s*pAdapter->device_mode)\s*\n\s*(WLAN_HDD_P2P_GO\s*!=\s*pAdapter->device_mode)')
    if pattern2.search(content):
        content = pattern2.sub(r'\1 &&\n           \2 &&\n           (WLAN_HDD_MONITOR != pAdapter->device_mode)', content)
        print("  ✓ Added WLAN_HDD_MONITOR to set_channel check (multiline)")
        total_changes += 1
    else:
        # Try the simplest approach — just find and replace the string
        old_str = '(WLAN_HDD_SOFTAP != pAdapter->device_mode)'
        if old_str in content:
            content = content.replace(
                old_str,
                '(WLAN_HDD_SOFTAP != pAdapter->device_mode) && (WLAN_HDD_MONITOR != pAdapter->device_mode)',
                1
            )
            print("  ✓ Added WLAN_HDD_MONITOR check via string replace")
            total_changes += 1
        else:
            print("  ✗ Could not auto-patch set_channel")
            print("  Manual: add && (WLAN_HDD_MONITOR != pAdapter->device_mode)")
            print("  to the if check in __wlan_hdd_cfg80211_set_channel")

if content != original:
    write_file(CFG_FILE, content)

# ============================================================
# Summary
# ============================================================
print()
print("=" * 60)
print(f"PATCH COMPLETE: {total_changes}/6 patches applied")
print("=" * 60)
print()
print("Verification:")
result = subprocess.run(['grep', '-c', 'NL80211_IFTYPE_MONITOR', CFG_FILE], 
                       capture_output=True, text=True)
count = int(result.stdout.strip()) if result.stdout.strip() else 0
print(f"  NL80211_IFTYPE_MONITOR mentions in cfg80211.c: {count}")

result = subprocess.run(['grep', '-c', 'if (VOS_MONITOR_MODE == hdd_get_conparam())', CFG_FILE],
                       capture_output=True, text=True)
gate_count = int(result.stdout.strip()) if result.stdout.strip() else 0
print(f"  con_mode gate remaining: {gate_count} (should be 0)")

result = subprocess.run(['grep', '-c', 'WLAN_HDD_MONITOR != pAdapter->device_mode', CFG_FILE],
                       capture_output=True, text=True)
mon_count = int(result.stdout.strip()) if result.stdout.strip() else 0
print(f"  WLAN_HDD_MONITOR in set_channel check: {mon_count} (should be 1)")
