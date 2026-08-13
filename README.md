# knatd

`knatd`（Kernel NAT Daemon）使用熟悉的 rinetd 四列配置格式，将端口映射转换为 Linux
iptables DNAT 规则。数据包始终由内核转发，不经过常驻用户态代理进程。

## 一行安装

```bash
curl -fsSL https://raw.githubusercontent.com/okai99/knatd/main/install.sh | sudo sh
```

安装程序会：

- 安装命令到 `/usr/local/sbin/knatd`
- 安装并启动 `knatd.service`
- 默认加载 `/etc/knatd/*.conf`
- 没有现有配置时生成 `/etc/knatd/default.conf`
- 参考配置中的规则全部处于注释状态，安装本身不会开放端口

## 配置

在 `/etc/knatd/` 中创建任意一个或多个 `.conf` 文件：

```text
# TCP：本机 8080 转发到 10.0.0.2:80
0.0.0.0 8080 10.0.0.2 80

# UDP
0.0.0.0 5353/udp 10.0.0.53 53/udp

# 指定监听地址和发往目标时使用的源地址
192.0.2.10 8443/tcp 10.0.0.3 443/tcp [src=10.0.0.1]
```

基本格式：

```text
监听地址 监听端口[/tcp|udp] 目标地址 目标端口[/tcp|udp] [src=IP]
```

TCP 是默认协议。目标端口没有注明协议时，会继承监听端口的协议。

修改配置后检查并重载：

```bash
sudo knatd check
sudo knatd render
sudo systemctl reload knatd
```

查看运行中的规则：

```bash
sudo knatd status
```

## 命令

```text
knatd check    检查全部配置
knatd render   预览将生成的 iptables 规则，不修改系统
knatd apply    应用全部配置
knatd status   查看 knatd 管理的规则
knatd clear    删除 knatd 管理的规则
```

`-c FILE_OR_DIR` 可以改用其他文件或目录，也可以重复传入：

```bash
sudo knatd -c /path/a.conf -c /path/conf.d apply
```

## 源地址与回程路由

默认启用 MASQUERADE，以接近 rinetd 的行为。目标服务器看到的客户端地址是
转发机地址，好处是不要求目标服务器配置特殊的回程路由。

如果目标服务器的回程流量确定会经过转发机，可以保留客户端真实 IP：

```bash
sudo knatd --no-masquerade apply
```

使用 systemd 时，需要同步修改 `knatd.service` 的 `ExecStart` 和 `ExecReload`。

## 与 rinetd 配置的差异

支持：

- IPv4 TCP 与 UDP
- 四列地址/端口映射
- `/tcp`、`/udp`
- `[src=IP]`
- 多个 `/etc/knatd/*.conf` 文件

`logfile`、`logcommon`、`pidlogfile` 会被忽略。以下功能会明确报错，因为它们
无法在保持相同语义的情况下直接转换为 iptables：

- `allow`、`deny`
- UDP `timeout`
- TCP 与 UDP 互转
- 域名、服务名、IPv6 和端口范围

## 安全与共存

工具只维护以下专用链：

```text
KNATD_DNAT
KNATD_OUTPUT
KNATD_FWD
KNATD_SNAT
```

它不会清空内置链或其他程序的链。每次修改前都会保存完整 IPv4 规则集，操作
失败则立即恢复；同时会等待 xtables 锁，降低与 Docker、Tailscale 等工具同时
修改防火墙时发生冲突的概率。

`--enable-ip-forward` 只会在运行时打开 IPv4 forwarding。若希望系统重启后
始终保持开启，请另外通过系统的 sysctl 配置持久化。

## 要求

- Linux
- Python 3.10+
- iptables、iptables-save、iptables-restore
- systemd（一行安装方式需要）

## 卸载

停止并禁用服务，清除 `knatd` 管理的 iptables 规则，然后删除程序和 systemd
单元：

```bash
sudo systemctl disable --now knatd.service
sudo /usr/local/sbin/knatd clear
sudo rm -f /usr/local/sbin/knatd /etc/systemd/system/knatd.service
sudo systemctl daemon-reload
```

卸载命令默认保留 `/etc/knatd` 中的配置。需要备份配置时：

```bash
sudo mv /etc/knatd /etc/knatd.backup
```

确定不再需要配置后，可以删除：

```bash
sudo rm -r /etc/knatd
```

## License

[MIT](LICENSE)
