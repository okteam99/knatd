# knatd

`knatd`（Kernel NAT Daemon）使用简洁的四列配置格式，将端口映射转换为 Linux
iptables DNAT 规则。数据包始终由内核转发，不经过常驻用户态代理进程。

## 使用流程

### 1. 安装

```bash
curl -fsSL https://raw.githubusercontent.com/okteam99/knatd/main/install.sh | sudo sh
```

安装程序会：

- 安装命令到 `/usr/local/sbin/knatd`
- 安装并启动 `knatd.service`
- 默认加载 `/etc/knatd/*.conf`
- 没有现有配置时生成 `/etc/knatd/default.conf`
- 参考配置中的规则全部处于注释状态，安装本身不会开放端口

### 2. 添加转发配置

直接编辑默认配置：

```bash
sudoedit /etc/knatd/default.conf
```

每行表示一条转发规则：

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

也可以按用途拆分成多个配置文件，例如 `/etc/knatd/web.conf` 和
`/etc/knatd/dns.conf`。程序会加载该目录下的全部 `.conf` 文件。

### 3. 检查并使配置生效

先检查配置；需要时可以预览将生成的规则：

```bash
sudo knatd check
sudo knatd render
```

`render` 不修改系统。确认无误后重新加载配置，再查看实际规则：

```bash
sudo knatd reload
sudo knatd status
```

### 4. 修改配置

编辑对应的 `.conf` 文件，完成后再次检查并重载：

```bash
sudoedit /etc/knatd/default.conf
sudo knatd check && sudo knatd reload
```

### 5. 删除配置

删除单条转发时，从对应文件中删除该行或在行首添加 `#`，然后重载。

删除整个独立配置文件时：

```bash
sudo rm /etc/knatd/web.conf
sudo knatd check && sudo knatd reload
```

建议保留 `/etc/knatd/default.conf`，即使其中只有注释。需要移除全部转发时，
清空或注释 `default.conf` 中的所有规则、删除其他 `.conf` 文件，然后重载服务。

## 命令

```text
knatd check    检查全部配置
knatd render   预览将生成的 iptables 规则，不修改系统
knatd reload   重新加载并应用全部配置
knatd status   查看 knatd 管理的规则
knatd clear    删除 knatd 管理的规则
knatd uninstall 卸载服务和程序
```

`-c FILE_OR_DIR` 可以改用其他文件或目录，也可以重复传入：

```bash
sudo knatd -c /path/a.conf -c /path/conf.d reload
```

## 源地址与回程路由

默认启用 MASQUERADE。目标服务器看到的客户端地址是转发机地址，好处是不要求
目标服务器配置特殊的回程路由。

如果目标服务器的回程流量确定会经过转发机，可以保留客户端真实 IP：

```bash
sudo knatd --no-masquerade reload
```

使用 systemd 时，需要同步修改 `knatd.service` 的 `ExecStart` 和 `ExecReload`。

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

运行内置卸载命令：

```bash
sudo knatd uninstall
```

卸载前会询问是否删除当前已有的 `KNATD_*` 转发规则：

```text
Remove existing knatd forwarding rules before uninstall? [Y/n]:
```

- 回车、`y`：清理规则后卸载
- `n`：保留当前规则并卸载；规则会持续到系统重启或手动清理，但不会再自动恢复

自动化环境可以跳过询问，明确指定处理方式：

```bash
sudo knatd uninstall --clear-rules
sudo knatd uninstall --keep-rules
```

两种方式都默认保留 `/etc/knatd` 中的配置。需要备份配置时：

```bash
sudo mv /etc/knatd /etc/knatd.backup
```

确定不再需要配置后，可以删除：

```bash
sudo rm -r /etc/knatd
```

## License

[MIT](LICENSE)
