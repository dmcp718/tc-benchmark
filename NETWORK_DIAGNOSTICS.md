# Network Performance Diagnostics

## Your VM Configuration

**Detected Setup:**
- Hypervisor: KVM (QEMU/Proxmox)
- Network Interface: ens18 (VirtIO)
- Network Driver: fq_codel queue discipline
- TCP Congestion Control: cubic
- Local IP: 192.168.8.210/24

## Why Upload Speed is Slow (~2.5 Mb/s vs 1Gb Expected)

### Root Causes

1. **Virtualization Overhead**
   - VirtIO network driver adds latency
   - CPU sharing can cause packet processing delays
   - Memory ballooning may impact buffers

2. **Host-Level Bandwidth Throttling**
   - Proxmox/KVM QoS settings may limit VM bandwidth
   - Check Proxmox web UI: VM > Hardware > Network Device > Rate limit

3. **TCP Window Scaling Issues**
   - Some observed connections show low throughput despite low RTT
   - Window scaling may not be optimal for VM environment

4. **Shared Infrastructure**
   - Multiple VMs on same host compete for bandwidth
   - Physical NIC may be shared/oversubscribed
   - Network storage (if used) consumes bandwidth

5. **ISP/Network Path Issues**
   - Actual fiber connection may not deliver full 1Gb
   - Carrier-grade NAT or traffic shaping
   - Peering/routing inefficiencies

## Diagnostic Commands

### Check Current Network Performance

```bash
# Test bandwidth to known-good server
sudo apt install iperf3
iperf3 -c speedtest.tele2.net

# Check network interface stats
ip -s link show ens18

# Monitor real-time bandwidth
sudo apt install iftop
sudo iftop -i ens18

# Check TCP/network tuning
sysctl net.ipv4.tcp_window_scaling
sysctl net.core.rmem_max
sysctl net.core.wmem_max
```

### Check for Proxmox Rate Limiting

On the **Proxmox host** (not VM), check:

```bash
# List VM network configs
grep -r "rate" /etc/pve/qemu-server/*.conf

# Example output showing 100Mb rate limit:
# net0: virtio=XX:XX:XX:XX:XX:XX,bridge=vmbr0,rate=100
```

Rate is in Megabits/sec. If you see `rate=100`, that's a 100Mb/s limit.

### Check for Bandwidth Contention

```bash
# Monitor network interface queue drops
netstat -i

# Check for packet loss
ping -c 100 8.8.8.8 | grep loss

# Check MTU
ip link show ens18 | grep mtu
# Should be 1500 for standard Ethernet
```

## Solutions

### 1. Remove Proxmox Rate Limiting

On Proxmox host:
```bash
# Edit VM config (replace 100 with your VM ID)
vi /etc/pve/qemu-server/100.conf

# Remove or increase "rate=" parameter from net0/net1 line
# Example: Change from rate=100 to rate=1000 or remove rate entirely
```

Then reboot VM or reload network config.

### 2. Optimize TCP Settings in VM

```bash
# Increase TCP buffer sizes
sudo sysctl -w net.core.rmem_max=134217728
sudo sysctl -w net.core.wmem_max=134217728
sudo sysctl -w net.ipv4.tcp_rmem="4096 87380 67108864"
sudo sysctl -w net.ipv4.tcp_wmem="4096 65536 67108864"

# Enable TCP window scaling (should already be on)
sudo sysctl -w net.ipv4.tcp_window_scaling=1

# Make permanent
sudo tee -a /etc/sysctl.conf <<EOF
net.core.rmem_max=134217728
net.core.wmem_max=134217728
net.ipv4.tcp_rmem=4096 87380 67108864
net.ipv4.tcp_wmem=4096 65536 67108864
net.ipv4.tcp_window_scaling=1
EOF
```

### 3. Use VirtIO Network Optimizations

On Proxmox host, optimize VM network device:
```bash
# Edit VM config
# Change network from:
# net0: virtio=XX:XX:XX:XX:XX:XX,bridge=vmbr0
# To:
# net0: virtio=XX:XX:XX:XX:XX:XX,bridge=vmbr0,firewall=0

# Or use SR-IOV/passthrough if available (best performance)
```

### 4. Check MTU Size

```bash
# Test if jumbo frames help (requires support from network path)
sudo ip link set ens18 mtu 9000

# Test
ping -M do -s 8972 192.168.8.1

# If successful, make permanent in /etc/netplan/ or /etc/network/interfaces
```

### 5. Switch TCP Congestion Control

```bash
# Try BBR (better for high-latency networks)
sudo modprobe tcp_bbr
sudo sysctl -w net.ipv4.tcp_congestion_control=bbr
sudo sysctl -w net.core.default_qdisc=fq

# Test performance
# If better, make permanent
echo "tcp_bbr" | sudo tee -a /etc/modules
sudo tee -a /etc/sysctl.conf <<EOF
net.ipv4.tcp_congestion_control=bbr
net.core.default_qdisc=fq
EOF
```

## Testing Upload Speed

### Simple Test
```bash
# Upload test using curl
dd if=/dev/zero bs=1M count=100 | curl -T - http://speedtest.tele2.net/upload.php

# Time a large upload
time curl -T large_file.bin http://your-server.com/upload
```

### Comprehensive Test with iperf3

On a remote server with good connectivity:
```bash
# Server side
iperf3 -s
```

From your VM:
```bash
# Upload (client to server)
iperf3 -c remote-server-ip -t 30

# Download (server to client)
iperf3 -c remote-server-ip -t 30 -R

# Parallel streams
iperf3 -c remote-server-ip -t 30 -P 4
```

## Expected Results After Optimization

- **LAN (to Proxmox host):** 500-900 Mb/s
- **Internet (1Gb fiber):** 500-950 Mb/s (depending on ISP/path)
- **With rate limiting removed:** Should match host capabilities

## Contact Your Hosting Provider

If you're on a cloud/VPS provider:
- Ask about network rate limits on your plan
- Request bandwidth upgrade if limited
- Ask if they offer SR-IOV or dedicated NICs
- Check if they throttle certain protocols (HTTP/SSH vs IPERF)

## Claude Code Upload Performance

The slow upload you're experiencing affects:
- File uploads to the session
- Git pushes with large commits
- Package downloads (if proxied through client)

**Workarounds:**
1. Use `git` directly in VM instead of uploading code
2. Download packages directly in VM (`apt`, `npm`, `pip`)
3. Use `scp`/`rsync` from a machine with better connectivity
4. Request network upgrade from hosting provider

## Quick Bandwidth Test

```bash
# Install speedtest-cli
sudo apt install speedtest-cli

# Run speed test
speedtest-cli

# Or use fast.com (Netflix)
curl -s https://fast.com
```

This will show if the issue is:
- **< 10 Mb/s**: Severe throttling or network issue
- **10-100 Mb/s**: Moderate limiting (common for budget VPS)
- **100-500 Mb/s**: Some overhead but reasonable
- **500-1000 Mb/s**: Near-optimal performance
