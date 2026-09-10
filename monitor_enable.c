#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <linux/wireless.h>
#include <unistd.h>
#include <stdlib.h>

int send_priv_ioctl(const char *ifname, const char *name, __s32 *args, int num_args) {
    int sock;
    struct iwreq wrq;
    struct iw_priv_args priv_args[64];
    
    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) { perror("socket"); return -1; }
    
    memset(&wrq, 0, sizeof(wrq));
    strncpy(wrq.ifr_name, ifname, IFNAMSIZ);
    wrq.u.data.pointer = priv_args;
    wrq.u.data.length = 64;
    
    if (ioctl(sock, SIOCGIWPRIV, &wrq) < 0) {
        perror("SIOCGIWPRIV");
        close(sock);
        return -1;
    }
    
    int num = wrq.u.data.length;
    int found_cmd = -1;
    int i;
    
    for (i = 0; i < num; i++) {
        if (strcmp(priv_args[i].name, name) == 0) {
            found_cmd = priv_args[i].cmd;
            printf("Found '%s': cmd=0x%x\n", name, found_cmd);
            break;
        }
    }
    
    if (found_cmd < 0) {
        fprintf(stderr, "ioctl '%s' not found\n", name);
        close(sock);
        return -1;
    }
    
    memset(&wrq, 0, sizeof(wrq));
    strncpy(wrq.ifr_name, ifname, IFNAMSIZ);
    wrq.u.data.pointer = args;
    wrq.u.data.length = num_args;
    wrq.u.data.flags = 1;
    
    if (ioctl(sock, found_cmd, &wrq) < 0) {
        perror("ioctl");
        close(sock);
        return -1;
    }
    
    printf("  OK '%s' sent\n", name);
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
    
    __s32 monitor_arg = 1;
    if (send_priv_ioctl(ifname, "monitor", &monitor_arg, 1) < 0) {
        fprintf(stderr, "Failed to set monitor state\n");
        return 1;
    }
    
    __s32 config_args[5];
    config_args[0] = channel;
    config_args[1] = 20;
    config_args[2] = 1;
    config_args[3] = 0xFFFF0000;
    config_args[4] = 1;
    
    if (send_priv_ioctl(ifname, "configureMonitorMode", config_args, 5) < 0) {
        fprintf(stderr, "Warning: configureMonitorMode not found\n");
    }
    
    printf("Monitor mode ENABLED on %s\n", ifname);
    return 0;
}
