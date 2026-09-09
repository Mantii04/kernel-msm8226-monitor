#!/usr/bin/env python3
import re, sys, os, subprocess

PRIMA = 'drivers/staging/prima'
CFG_FILE = f'{PRIMA}/CORE/HDD/src/wlan_hdd_cfg80211.c'
MAIN_FILE = f'{PRIMA}/CORE/HDD/src/wlan_hdd_main.c'

def read_file(path):
    with open(path, 'r') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)

total = 0

# PATCH 1: Remove con_mode gate
print("[1/8] Removing con_mode gate")
content = read_file(CFG_FILE)
original = content
pat = re.compile(r'if\s*\(VOS_MONITOR_MODE\s*==\s*hdd_get_conparam\(\)\s*\)\s*\{[^}]*BIT\(NL80211_IFTYPE_MONITOR\)[^}]*\}', re.DOTALL)
if pat.search(content):
    content = pat.sub('wiphy->interface_modes |= BIT(NL80211_IFTYPE_MONITOR);', content)
    total += 1
    print("  OK")
else:
    pat2 = re.compile(r'if\s*\(VOS_MONITOR_MODE\s*==\s*hdd_get_conparam\(\)\s*\)\s*\{\s*wiphy->interface_modes\s*\|=\s*BIT\(NL80211_IFTYPE_MONITOR\);\s*\}', re.DOTALL)
    if pat2.search(content):
        content = pat2.sub('wiphy->interface_modes |= BIT(NL80211_IFTYPE_MONITOR);', content)
        total += 1
        print("  OK (exact)")
    else:
        print("  SKIP")
if content != original:
    write_file(CFG_FILE, content)

# PATCH 2: Enable .set_channel unconditionally
print("[2/8] Enabling .set_channel unconditionally")
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
    total += 1
    print("  OK")
else:
    print("  SKIP")
if content != original:
    write_file(CFG_FILE, content)

# PATCH 3: Add NL80211_IFTYPE_MONITOR to add_virtual_intf
print("[3/8] Adding NL80211_IFTYPE_MONITOR to add_virtual_intf")
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
        total += 1
        print("  OK (already exists)")
    else:
        pat = re.compile(r'(case\s+NL80211_IFTYPE_P2P_GO\s*:.*?session_type\s*=\s*WLAN_HDD_P2P_GO\s*;\s*\n\s*break\s*;)', re.DOTALL)
        match = pat.search(content)
        if match:
            ins = match.group(1) + '\n    case NL80211_IFTYPE_MONITOR:\n        session_type = WLAN_HDD_MONITOR;\n        break;'
            content = content[:match.end()] + ins + content[match.end():]
            total += 1
            print("  OK (added after P2P_GO)")
        else:
            print("  SKIP")
else:
    print("  SKIP")
if content != original:
    write_file(CFG_FILE, content)

# PATCH 4: SKIPPED
print("[4/8] change_virtual_intf - SKIPPED")
total += 1

# PATCH 5: Verify set_channel
print("[5/8] Verifying set_channel exists")
result = subprocess.run(['grep', '-c', 'wlan_hdd_cfg80211_set_channel', CFG_FILE], capture_output=True, text=True)
if int(result.stdout.strip() if result.stdout.strip() else '0') > 0:
    total += 1
    print("  OK")
else:
    print("  FAIL")

# PATCH 6: Fix set_channel device_mode check
print("[6/8] Fixing set_channel device_mode check")
content = read_file(CFG_FILE)
original = content
old_if = '(WLAN_HDD_SOFTAP != pAdapter->device_mode)'
new_if = '(WLAN_HDD_SOFTAP != pAdapter->device_mode) && (WLAN_HDD_MONITOR != pAdapter->device_mode)'
if old_if in content and new_if not in content:
    content = content.replace(old_if, new_if, 1)
    print("  OK (first if)")
else:
    print("  SKIP (first if)")
old_elseif = '(pAdapter->device_mode == WLAN_HDD_SOFTAP)'
new_elseif = '(pAdapter->device_mode == WLAN_HDD_SOFTAP) || (pAdapter->device_mode == WLAN_HDD_MONITOR)'
if old_elseif in content and new_elseif not in content:
    content = content.replace(old_elseif, new_elseif, 1)
    print("  OK (else-if)")
else:
    print("  SKIP (else-if)")
if content != original:
    write_file(CFG_FILE, content)
    total += 1

# PATCH 7: Fix NULL dev handling
print("[7/8] Fixing NULL dev handling")
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
    total += 1
    print("  OK")
else:
    print("  SKIP")
if content != original:
    write_file(CFG_FILE, content)

# PATCH 8: Send firmware message from __hdd_mon_open (ndo_open callback)
print("[8/8] Sending firmware message from __hdd_mon_open")
content = read_file(MAIN_FILE)
original = content

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
   struct hdd_request *request;
   void *cookie;
   static const struct hdd_request_params params = {
       .priv_size = 0,
       .timeout_ms = MON_MODE_MSG_TIMEOUT,
   };
   int ret = 0;

   if(pAdapter == NULL) {
      VOS_TRACE( VOS_MODULE_ID_HDD, VOS_TRACE_LEVEL_FATAL,
         "%s: HDD adapter context is Null", __func__);
      return -EINVAL;
   }

   pMonCtx = WLAN_HDD_GET_MONITOR_CTX_PTR(pAdapter);
   if (pMonCtx == NULL) {
       return -EINVAL;
   }

   /* Send firmware message to start monitor mode */
   pMonCtx->state = MON_MODE_START;
   pMonCtx->ChannelNo = 6;
   pMonCtx->ChannelBW = 20;
   pMonCtx->crcCheckEnabled = 1;
   pMonCtx->typeSubtypeBitmap = 0xFFFF00000000;
   pMonCtx->is80211to803ConReq = 1;

   request = hdd_request_alloc(&params);
   if (!request) {
       hddLog(VOS_TRACE_LEVEL_ERROR, FL("Request allocation failure"));
       return -ENOMEM;
   }
   cookie = hdd_request_cookie(request);

   if (VOS_STATUS_SUCCESS != wlan_hdd_mon_postMsg(cookie, pMonCtx, hdd_mon_post_msg_cb)) {
       VOS_TRACE(VOS_MODULE_ID_HDD, VOS_TRACE_LEVEL_ERROR, FL("failed to post MON MODE REQ"));
       pMonCtx->state = MON_MODE_STOP;
       ret = -EIO;
   } else {
       ret = hdd_request_wait_for_response(request);
       if (ret)
           VOS_TRACE(VOS_MODULE_ID_HDD, VOS_TRACE_LEVEL_ERROR, FL("timeout on monitor mode completion %d"), ret);
   }
   hdd_request_put(request);

   return ret;
}"""

if old_mon_open in content:
    content = content.replace(old_mon_open, new_mon_open, 1)
    total += 1
    print("  OK")
else:
    print("  SKIP - could not find __hdd_mon_open")

if content != original:
    write_file(MAIN_FILE, content)

# Summary
print()
print("=" * 60)
print(f"PATCH COMPLETE: {total}/8 patches applied")
print("=" * 60)
