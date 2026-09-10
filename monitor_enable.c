#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <linux/wireless.h>
#include <unistd.h>
#include <stdlib.h>

/* Handler 1: iw_setint_getnone at SIOCIWFIRSTPRIV + 0 
   Reads sub_cmd from args[0], value from args[1] */
int send_setint_getnone(const char *ifname, int sub_cmd, int value) {
    int sock;
    struct iwreq wrq;
    __s32 args[2];
    
    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) { perror("socket"); return -1; }
    
    args[0] = sub_cmd;
    args[1] = value;
    
    memset(&wrq, 0, sizeof(wrq));
    strncpy(wrq.ifr_name, ifname, IFNAMSIZ);
    wrq.u.data.pointer = args;
    wrq.u.data.length = 2;
    
    if (ioctl(sock, SIOCIWFIRSTPRIV, &wrq) < 0) {
        perror("ioctl(SIOCIWFIRSTPRIV)");
        close(sock);
        return -1;
    }
    
    printf("  OK setint_getnone sub_cmd %d\n", sub_cmd);
    close(sock);
    return 0;
}

/* Handler 2: iw_hdd_set_var_ints_getnone at SIOCIWFIRSTPRIV + 7
   Reads sub_cmd from wrqu->data.flags, args from pointer */
int send_set_var_ints_getnone(const char *ifname, int sub_cmd, __s32 *args, int num_args) {
    int sock;
    struct iwreq wrq;
    
    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) { perror("socket"); return -1; }
    
    memset(&wrq, 0, sizeof(wrq));
    strncpy(wrq.ifr_name, ifname, IFNAMSIZ);
    wrq.u.data.flags = sub_cmd;
    wrq.u.data.pointer = args;
    wrq.u.data.length = num_args;
    
    if (ioctl(sock, SIOCIWFIRSTPRIV + 7, &wrq) < 0) {
        perror("ioctl(SIOCIWFIRSTPRIV + 7)");
        close(sock);
        return -1;
    }
    
    printf("  OK set_var_ints_getnone sub_cmd %d\n", sub_cmd);
    close(sock);
    return 0;
}

int main(int argc, char *argv[]) {
    char *ifname;
    
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <interface> [channel]\n", argv[0]);
        return 1;
    }
    ifname = argv[1];
    
    int channel = 6;
    if (argc >= 3) channel = atoi(argv[2]);
    
    printf("Enabling monitor mode on %s (channel %d)...\n", ifname, channel);
    
    /* Step 1: Set monitor state to START (WE_SET_MONITOR_STATE = 22) 
       This toggles pMonCtx->state to MON_MODE_START */
    if (send_setint_getnone(ifname, 22, 1) < 0) {
        fprintf(stderr, "Failed to set monitor state\n");
        return 1;
    }
    
    /* Step 2: Configure monitor mode (WE_CONFIGURE_MONITOR_MODE = 10)
       This sends the firmware message because state is now MON_MODE_START */
    __s32 config_args[5];
    config_args[0] = channel;
    config_args[1] = 20;
    config_args[2] = 1;
    config_args[3] = 111; /* Capture all frame types */
    config_args[4] = 1;
    
    if (send_set_var_ints_getnone(ifname, 10, config_args, 5) < 0) {
        fprintf(stderr, "Failed to configure monitor mode\n");
        return 1;
    }
    
    printf("Monitor mode ENABLED on %s (channel %d)\n", ifname, channel);
    return 0;
}
