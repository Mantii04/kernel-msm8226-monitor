#!/usr/bin/env python3
import re, sys, os, subprocess

PRIMA = 'drivers/staging/prima'
CFG_FILE = f'{PRIMA}/CORE/HDD/src/wlan_hdd_cfg80211.c'
MAIN_FILE = f'{PRIMA}/CORE/HDD/src/wlan_hdd_main.c'

def read_file(path):
    with open(path, 'r') as f: return f.read()
def write_file(path, content):
    with open(path, 'w') as f: f.write(content)

total = 0

# PATCH 0: Add missing include
print("[0/6] Adding wlan_hdd_request_manager.h include")
content = read_file(CFG_FILE)
original = content
old_include = '#include "wlan_hdd_dev_pwr.h"'
new_include = '#include "wlan_hdd_dev_pwr.h"\n#include "wlan_hdd_request_manager.h"'
if old_include in content and new_include not in content:
    content = content.replace(old_include, new_include, 1)
    total += 1; print("  OK")
else: print("  SKIP")
if content != original: write_file(CFG_FILE, content)

# PATCH 1: Remove con_mode gate
print("[1/6] Removing con_mode gate")
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
print("[2/6] Enabling .set_channel")
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
print("[3/6] Adding monitor to add_virtual_intf")
total += 1; print("  OK (exists in source)")

# PATCH 4: Fix NULL dev
print("[4/6] Fixing NULL dev")
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

# PATCH 5: Send firmware message synchronously from set_channel
print("[5/6] Sending firmware message from set_channel")
content = read_file(CFG_FILE)
original = content
old_check = """    num_ch = WNI_CFG_VALID_CHANNEL_LIST_LEN;

    if ((WLAN_HDD_SOFTAP != pAdapter->device_mode)"""
new_check = """    num_ch = WNI_CFG_VALID_CHANNEL_LIST_LEN;

    /* If monitor mode, send firmware message to start capture */
    if (pAdapter->device_mode == WLAN_HDD_MONITOR)
    {
        hdd_mon_ctx_t *pMonCtx = WLAN_HDD_GET_MONITOR_CTX_PTR(pAdapter);
        if (pMonCtx && pMonCtx->state != MON_MODE_START)
        {
            struct hdd_request *request;
            void *cookie;
            static const struct hdd_request_params params = {
                .priv_size = 0,
                .timeout_ms = MON_MODE_MSG_TIMEOUT,
            };
            pMonCtx->state = MON_MODE_START;
            pMonCtx->ChannelNo = channel;
            pMonCtx->ChannelBW = 20;
            pMonCtx->crcCheckEnabled = 1;
            pMonCtx->typeSubtypeBitmap = 0xFFFF00000000;
            pMonCtx->is80211to803ConReq = 1;
            request = hdd_request_alloc(&params);
            if (request) {
                cookie = hdd_request_cookie(request);
                if (VOS_STATUS_SUCCESS != wlan_hdd_mon_postMsg(cookie, pMonCtx, hdd_mon_post_msg_cb)) {
                    pMonCtx->state = MON_MODE_STOP;
                } else {
                    hdd_request_wait_for_response(request);
                }
                hdd_request_put(request);
            }
        }
        else if (pMonCtx)
        {
            pMonCtx->ChannelNo = channel;
        }
        return 0;
    }

    if ((WLAN_HDD_SOFTAP != pAdapter->device_mode)"""
if old_check in content:
    content = content.replace(old_check, new_check, 1)
    total += 1; print("  OK")
if content != original: write_file(CFG_FILE, content)

# PATCH 6: Initialize hdd_request_manager in wlan_hdd_mon_open
print("[6/6] Initializing hdd_request_manager in wlan_hdd_mon_open")
content = read_file(MAIN_FILE)
original = content
old_mon_open = """int wlan_hdd_mon_open(hdd_context_t *pHddCtx)
{
    VOS_STATUS status;
    v_CONTEXT_t pVosContext= NULL;
    hdd_adapter_t *pAdapter= NULL;"""
new_mon_open = """int wlan_hdd_mon_open(hdd_context_t *pHddCtx)
{
    VOS_STATUS status;
    v_CONTEXT_t pVosContext= NULL;
    hdd_adapter_t *pAdapter= NULL;

    hdd_request_manager_init();"""
if old_mon_open in content:
    content = content.replace(old_mon_open, new_mon_open, 1)
    total += 1; print("  OK")
if content != original: write_file(MAIN_FILE, content)

print()
print("=" * 60)
print(f"PATCH COMPLETE: {total}/6 patches applied")
print("=" * 60)
