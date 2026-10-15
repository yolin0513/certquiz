#!/usr/bin/env bash
# 推送閘門：推送一律走這支，不直接下 git push（hook 可以被 --no-verify 繞過，這支不會）。
#
# 順序：鎖定 commit → 工作區要乾淨 → 全部測試 → 整段歷史掃描 → 隱私檢查 → 題庫建置檢查 → 只推鎖定的 commit → 比對遠端
# 用法：bash scripts/pushsafe.sh [遠端名稱，預設 origin]
# 結束碼：0 推送成功且遠端＝鎖定的 commit；1 推送前任一關擋下；2 推送失敗；3 遠端≠鎖定的 commit；
#         5 推上去的是鎖定的 commit，但推送期間本機 main 又多了 commit（那些沒推、沒檢查）
set -u
REMOTE="${1:-origin}"
cd "$(git rev-parse --show-toplevel)" || exit 1

say() { printf 'PUSHSAFE: %s\n' "$*"; }
die() { say "擋下：$*"; exit 1; }

branch="$(git symbolic-ref --short -q HEAD || true)"
[ "$branch" = "main" ] || die "HEAD 不在 main 上（現在是 ${branch:-分離的 HEAD}）"
PIN="$(git rev-parse HEAD)"
say "鎖定 commit $PIN"
# 白名單：刻意不進版控、又不能用 .gitignore 排除的路徑（docs/STATUS.md「已知平台行為」：桌面版檔案窗格看不到 gitignored 路徑，實測）。
# 只放行這些路徑底下「沒追蹤」的檔（?? 開頭）；暫存了的、改過的、任何其他位置的未追蹤檔照樣擋。
# 一個路徑一個具名例外，不要改成萬用（test_pushsafe.py 情境 G 與 --mutate 驗這件事）。
#   給使用者/：所有要給使用者看的產出（教材 HTML、抽檢單、重點整理）；產生它們的腳本直接寫到這裡。自查 R1（路徑）＋R7（題幹）擋，進不了 commit
UNTRACKED_OK='^\?\? 給使用者/'
dirty="$(git -c core.quotePath=false status --porcelain -uall | grep -Ev "$UNTRACKED_OK" || true)"
[ -z "$dirty" ] || die "工作區不乾淨（有沒 commit 的改動或沒追蹤的檔）：$(printf '%s' "$dirty" | head -3 | tr '\n' ' ')"
git remote get-url "$REMOTE" >/dev/null 2>&1 || die "沒有遠端 $REMOTE"
[ "$(git config core.hooksPath)" = ".githooks" ] || die "core.hooksPath 不是 .githooks（新 clone 要先下 git config core.hooksPath .githooks）"

run() { say "跑：$*"; "$@" || die "$* 沒過"; }
run python -I scripts/selfcheck.py --selftest
run python -I scripts/check_privacy.py --selftest
run python -I scripts/test_build_data.py
run node scripts/test_logic.mjs
run python -I scripts/test_verify_live.py
run python -I scripts/test_verify_basis.py
run python -I scripts/selfcheck.py --history
run python -I scripts/check_privacy.py
run python -I scripts/build_data.py --check

[ "$(git rev-parse HEAD)" = "$PIN" ] || die "檢查期間 HEAD 變了（$PIN → $(git rev-parse HEAD)），重跑"
say "推送 $PIN 到 $REMOTE main"
git push "$REMOTE" "$PIN:refs/heads/main" || { say "推送失敗"; exit 2; }
remote_sha="$(git ls-remote "$REMOTE" refs/heads/main | cut -f1)"
[ "$remote_sha" = "$PIN" ] || { say "遠端 main 是 $remote_sha，不是鎖定的 $PIN"; exit 3; }
if [ "$(git rev-parse main)" != "$PIN" ]; then
  say "推上去的是鎖定的 $PIN；但推送期間本機 main 多了 commit（$(git rev-parse main)），那些沒推、沒檢查"
  exit 5
fi
say "推送成功：遠端 main ＝ $PIN"
exit 0
