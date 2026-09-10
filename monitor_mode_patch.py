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

# PATCH 1: Remove con_mode gate
print("[1/5] Removing con_mode gate")
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
print("[2/5] Enabling .set_channel")
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

# PATCH 3: Fix NULL dev in set_channel
print("[3/5] Fixing NULL dev in set_channel")
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

# PATCH 4: Store channel in monitor context in set_channel (no firmware message)
print("[4/5] Storing channel in monitor context")
content = read_file(CFG_FILE)
original = content
old_check = """    num_ch = WNI_CFG_VALID_CHANNEL_LIST_LEN;

    if ((WLAN_HDD_SOFTAP != pAdapter->device_mode)"""
new_check = """    num_ch = WNI_CFG_VALID_CHANNEL_LIST_LEN;

    /* If monitor mode, just store the channel */
    if (pAdapter->device_mode == WLAN_HDD_MONITOR)
    {
        hdd_mon_ctx_t *pMonCtx = WLAN_HDD_GET_MONITOR_CTX_PTR(pAdapter);
        if (pMonCtx)
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

# PATCH 5: Send firmware message from __hdd_mon_open (ndo_open) with NULL-safe callback
print("[5/5] Sending firmware message from __hdd_mon_open")
content = read_file(MAIN_FILE)
original = content

# Fix the callback to be NULL-safe
old_cb = """void hdd_mon_post_msg_cb(void *context)
{
    struct hdd_request *request;

    request = hdd_request_get(context);
    if (!request) {
        hddLog(VOS_TRACE_LEVEL_ERROR, FL("Obsolete request"));
        return;
    }

    hdd_request_complete(request);
    hdd_request_put(request);

    return;
}"""
new_cb = """void hdd_mon_post_msg_cb(void *context)
{
    struct hdd_request *request;

    if (!context) return;

    request = hdd_request_get(context);
    if (!request) {
        hddLog(VOS_TRACE_LEVEL_ERROR, FL("Obsolete request"));
        return;
    }

    hdd_request_complete(request);
    hdd_request_put(request);

    return;
}"""
if old_cb in content:
    content = content.replace(old_cb, new_cb, 1)
    print("  OK (callback NULL-safe)")

# Add firmware message to __hdd_mon_open
old_mon_open = """int __hdd_mon_open (struct net_device *dev)
{
   hdd_adapter_t *pAdapter = WLAN_HDD_GET_PRIV_PTR(dev);

   if(pAdapter == NULL) {
      VOS_TRACE( VOS_MODULE_ID_HDD, VOS_TRACE_LEVEL_FATAL,
         "%s: HDD adapter context is Null", __func__);
      return -EINVAL;
   }

   return 0;
}"""
new_mon_open = """int __hdd_mon_open (struct net_device *dev)
{
   hdd_adapter_t *pAdapter = WLAN_HDD_GET_PRIV_PTR(dev);
   hdd_mon_ctx_t *pMonCtx;

   if(pAdapter == NULL) {
      VOS_TRACE( VOS_MODULE_ID_HDD, VOS_TRACE_LEVEL_FATAL,
         "%s: HDD adapter context is Null", __func__);
      return -EINVAL;
   }

   /* Send firmware message to start monitor mode capture */
   pMonCtx = WLAN_HDD_GET_MONITOR_CTX_PTR(pAdapter);
   if (pMonCtx && pMonCtx->state != MON_MODE_START)
   {
       pMonCtx->state = MON_MODE_START;
       pMonCtx->ChannelNo = 6;
       pMonCtx->ChannelBW = 20;
       pMonCtx->crcCheckEnabled = 1;
       pMonCtx->typeSubtypeBitmap = 0xFFFF00000000;
       pMonCtx->is80211to803ConReq = 1;
       wlan_hdd_mon_postMsg(NULL, pMonCtx, hdd_mon_post_msg_cb);
       hddLog(VOS_TRACE_LEVEL_INFO, "%s: Monitor mode firmware message sent", __func__);
   }

   return 0;
}"""
if old_mon_open in content:
    content = content.replace(old_mon_open, new_mon_open, 1)
    total += 1; print("  OK (mon_open)")
if content != original: write_file(MAIN_FILE, content)

print()
print("=" * 60)
print(f"PATCH COMPLETE: {total}/5 patches applied")
print("=" * 60)
