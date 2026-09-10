#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <linux/wireless.h>
#include <unistd.h>
#include <stdlib.h>

int send_raw_ioctl(const char *ifname, int sub_cmd, __s32 *args, int num_args) {
    int sock;
    struct iwreq wrq;
    
    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) { perror("socket"); return -1; }
    
    memset(&wrq, 0, sizeof(wrq));
    strncpy(wrq.ifr_name, ifname, IFNAMSIZ);
    
    /* The driver's iw_setint_getnone expects the sub_cmd to be the first element */
    /* But we can't pass 6 args easily if sub_cmd takes one. 
       Actually, iw_setint_getnone reads sub_cmd from wrq.u.data.flags? No, it reads from args.
       Let's pack sub_cmd into the flags, and args into the pointer.
    */
    wrq.u.data.flags = sub_cmd;
    wrq.u.data.pointer = args;
    wrq.u.data.length = num_args;
    
    /* WLAN_PRIV_SET_INT_GET_NONE is SIOCIWFIRSTPRIV */
    if (ioctl(sock, SIOCIWFIRSTPRIV, &wrq) < 0) {
        perror("ioctl(SIOCIWFIRSTPRIV)");
        close(sock);
        return -1;
    }
    
    printf("  OK sub_cmd %d sent\n", sub_cmd);
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
    
    /* WE_SET_MONITOR_STATE is 22. It takes 1 arg (1 to start) */
    __s32 start_arg = 1;
    if (send_raw_ioctl(ifname, 22, &start_arg, 1) < 0) {
        fprintf(stderr, "Failed to set monitor state\n");
        return 1;
    }
    
    /* WE_CONFIGURE_MONITOR_MODE is 10. It takes 5 args:
       channel, bw, crc, type, conversion */
    __s32 config_args[5];
    config_args[0] = channel;
    config_args[1] = 20;
    config_args[2] = 1;
    config_args[3] = 111; /* Capture all frame types */
    config_args[4] = 1;
    
    if (send_raw_ioctl(ifname, 10, config_args, 5) < 0) {
        fprintf(stderr, "Failed to configure monitor mode\n");
        return 1;
    }
    
    printf("Monitor mode ENABLED on %s (channel %d)\n", ifname, channel);
    return 0;
}
