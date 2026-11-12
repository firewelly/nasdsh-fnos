# shellcheck shell=bash
# NasDSH 新会话提示（仅在 CLI 退化为普通 shell 时出现）
case $- in
  *i*) ;;
  *) return ;;
esac

if [ "$SHLVL" = "1" ] && [ -z "$NASDSH_HINT_SHOWN" ]; then
  export NASDSH_HINT_SHOWN=1
  echo "┌──────────────────────────────────────────────────────────┐"
  echo "│ NasDSH —— DeepSeek Harness on NAS                        │"
  echo "│   dsh-tui             启动交互式 TUI                     │"
  echo "│   dsh-tui -p \"任务\"    一次性 CLI 任务                   │"
  echo "│   dsh web --help      Web 服务参数                       │"
  echo "│   首次使用: 在 Web 工作台 Settings → Models 配置模型     │"
  echo "│   升级: nasdsh-update（或页面右上角按钮）                │"
  echo "│   关闭浏览器页面会话保留；exit 结束本会话                │"
  echo "└──────────────────────────────────────────────────────────┘"
fi
