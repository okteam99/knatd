# knatd

`knatd`（Kernel NAT Daemon）使用简洁的四列配置格式，将端口映射转换为 Linux
iptables DNAT 规则。数据包由内核转发，不经过常驻用户态代理进程。

## 快速使用

### 1. 安装

```bash
curl -fsSL https://raw.githubusercontent.com/okteam99/knatd/main/install.sh | sudo sh
```

### 2. 添加转发

编辑默认配置：

```bash
sudoedit /etc/knatd/default.conf
```

添加一行，例如将本机 `8080` 转发到 `10.0.0.2:80`：

```text
0.0.0.0 8080 10.0.0.2 80
```

### 3. 使配置生效

```bash
sudo knatd reload
```

查看已加载的规则：

```bash
sudo knatd status
```

### 4. 删除配置

删除或注释配置文件中的规则，然后重新加载：

```bash
sudoedit /etc/knatd/default.conf
sudo knatd reload
```

如果使用独立配置文件，可以直接删除该文件：

```bash
sudo rm /etc/knatd/web.conf
sudo knatd reload
```

## 详细功能

### 安装内容

安装程序会：

- 安装命令到 `/usr/local/sbin/knatd`
- 安装并启动 `knatd.service`
- 默认加载 `/etc/knatd/*.conf`
- 没有现有配置时生成 `/etc/knatd/default.conf`
- 生成仅包含注释示例的默认配置，不会在安装时开放端口

### 配置格式

每行表示一条转发规则：

```text
监听地址 监听端口[/tcp|udp] 目标地址 目标端口[/tcp|udp] [src=IP]
```

示例：

```text
# TCP：本机 8080 转发到 10.0.0.2:80
0.0.0.0 8080 10.0.0.2 80

# UDP：本机 5353 转发到 10.0.0.53:53
0.0.0.0 5353/udp 10.0.0.53 53/udp

# 指定监听地址和发往目标时使用的源地址
192.0.2.10 8443/tcp 10.0.0.3 443/tcp [src=10.0.0.1]
```

TCP 是默认协议。目标端口没有注明协议时，会继承监听端口的协议。

可以按用途拆分成多个文件，例如 `/etc/knatd/web.conf` 和
`/etc/knatd/dns.conf`。`knatd reload` 会加载目录下的全部 `.conf` 文件。

建议保留 `/etc/knatd/default.conf`，即使其中只有注释。需要移除全部转发时，
清空或注释 `default.conf` 中的规则、删除其他 `.conf` 文件，然后执行
`sudo knatd reload`。

### 检查和预览

修改配置后可以先检查语法：

```bash
sudo knatd check
```

预览将生成的 iptables 规则，不修改系统：

```bash
sudo knatd render
```

确认无误后执行：

```bash
sudo knatd reload
```

### 命令

| 命令 | 用途 |
| --- | --- |
| `knatd check` | 检查全部配置 |
| `knatd render` | 预览规则，不修改系统 |
| `knatd reload` | 重新加载并应用全部配置 |
| `knatd status` | 查看当前管理的规则 |
| `knatd clear` | 清除当前管理的规则 |
| `knatd uninstall` | 卸载服务和程序 |

`-c FILE_OR_DIR` 可以改用其他文件或目录，也可以重复传入：

```bash
sudo knatd -c /path/a.conf -c /path/conf.d reload
```

### 源地址与回程路由

默认启用 MASQUERADE。目标服务器看到的客户端地址是转发机地址，因此不要求
目标服务器配置特殊回程路由。

如果目标服务器的回程流量确定会经过转发机，可以保留客户端真实 IP：

```bash
sudo knatd --no-masquerade reload
```

通过 systemd 使用此模式时，需要同步修改 `knatd.service` 的 `ExecStart` 和
`ExecReload`。

### 本机访问

默认情况下，本机发起的连接也会参与转发。因此配置 `0.0.0.0 2229 ...` 后，
可以通过 `127.0.0.1:2229` 验证：

```bash
ssh -p 2229 root@127.0.0.1
```

对通配监听地址启用本机访问时，`reload` 会同时打开运行时内核设置
`net.ipv4.conf.all.route_localnet`，让回环连接可以在 DNAT 后离开本机。

如果只希望转发从网络进入的连接，可以关闭本机转发：

```bash
sudo knatd --no-local-output reload
```

通过 systemd 使用此模式时，同样需要修改 `knatd.service` 的 `ExecStart` 和
`ExecReload`。

### 安全与共存

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

`knatd reload` 会按当前规则在运行时打开所需的 IPv4 路由设置；服务启动时会
重新设置，因此不需要另行持久化 sysctl 配置。

### 系统要求

- Linux
- Python 3.10+
- iptables、iptables-save、iptables-restore
- systemd（一行安装方式需要）

### 卸载

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

两种方式都保留 `/etc/knatd` 中的配置。需要备份配置时：

```bash
sudo mv /etc/knatd /etc/knatd.backup
```

确定不再需要配置后，可以删除：

```bash
sudo rm -r /etc/knatd
```

## License

[MIT](LICENSE)
