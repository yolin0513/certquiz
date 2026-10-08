#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
內控主題分類規則（docs/K_讀書模式方案.md 第 2 步）
-------------------------------------------------------------------------------
主題範圍是讀過開發組（split.json 的 dev）之後定的；規則只用開發組調整，驗收組只靠規則分類、不手動調。
規則依順序比對，第一個命中的主題就是這題的主題；都沒命中放「其他」。比對文字：題幹＋正解。

用法：
  python scripts/study_topics.py --dev            只看開發組：各主題題數、其他的題數，並把分類明細寫到暫存檔供檢查
  python scripts/study_topics.py --freeze         凍結規則：把這支程式的 sha256 與時間記入 data/local/study/log.tsv
  python scripts/study_topics.py --apply          套用到全部題目（先核對這支程式與凍結時的雜湊相同，不同就拒絕），
                                                  輸出 data/local/study/topics.json（只在本機，只有題號與主題代號）
"""
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "data" / "local" / "import" / "bic-匯入包.json"
STUDY = ROOT / "data" / "local" / "study"

# (代號, 名稱, 範圍說明, 規則)。順序就是優先順序：越前面越具體。
# 規則是讀開發組之後定、只在開發組上調整的（2026-10-08，三輪）；驗收組只靠這些規則分類。
TOPICS = [
    ("T03", "自行查核", "一般與專案自行查核、自行查核負責人與報告、法令遵循自行評估",
     r"自行查核|自行選定|自行指派"),
    ("T14", "財富管理、信託與衍生性商品", "財富管理與理專、商品適合度、金融消費者保護與廣告、信託、衍生性與結構型商品、投資顧問",
     r"財富管理|理財|理專|適合度|金融消費者|廣告|業務招攬|信託|衍生性|結構型|避險|投資型金融商品|推介|投資顧問|全權委託"),
    ("T13", "外匯業務", "外匯收支申報、結匯、DBU 外匯存款、信用狀、光票、遠期外匯與 NDF、國際金融業務分行",
     r"外匯|結匯|結購|結售|信用狀|光票|外幣|匯率|國際金融業務|D/A|D/P|NDF|遠期外匯"),
    ("T04", "銀行法的授信與投資限制", "利害關係人授信、同一關係人、主要股東與法人股東、投資有價證券與轉投資限額、資本等級、信用期限",
     r"銀行法(?!規遵循)|利害關係|同一關係人|關係企業|主要股東|法人股東|資本等級|轉投資|核算基數|投資(?!顧問|型).{0,8}(?:有價證券|股票|事業)|銀行之負責人|銀行負責人"),
    ("T15", "票券、證券與金控", "票券金融、商業本票、證券經紀承銷與融資融券、債券與貨幣市場、金融控股公司",
     r"票券|商業本票|證券商|證券經紀|承銷|融資融券|融資總金額|債券市場|債券附條件|債票|公司債|貨幣市場|有價證券投資市場|金融控股公司法|金控公司|集中保管"),
    ("T11", "安全維護與金融犯罪防制", "安全維護、報警系統、庫房與保管箱、ATM 與錄影、詐騙通報、偽鈔偽卡、洗錢、警示帳戶、警察查詢、重大偶發事件",
     r"安全維護|報警|保管箱|自動櫃員機|ATM|錄影|側錄|盜錄|詐騙|偽卡|偽造卡|偽（變）造|偽變造|遭偽|洗錢|警示帳戶|警察|偶發事件|人頭"),
    ("T08", "信用卡", "發卡、額度、最低應繳、循環信用、信用卡呆帳與代收、學生卡、現金卡",
     r"信用卡|發卡機構|持卡人|現金卡"),
    ("T16", "作業委外", "金融機構作業委託他人處理的範圍與責任",
     r"委外|委託他人處理"),
    ("T06", "消費金融", "消費金融產品與行銷、消費者貸款、授信審核與詐冒風險",
     r"消費金融|消費者貸款|消費性貸款|消費性放款|冒貸|冒名|詐冒|財力證明"),
    ("T02", "內部稽核", "稽核單位與總稽核、稽核人員、查核頻率與稽核報告、稽核工作考核",
     r"內部稽核|稽核單位|稽核人員|總稽核|稽核報告|稽核計畫|稽核工作|一般查核|專案查核|場外監控"),
    ("T12", "資訊安全與電子銀行", "電子銀行安全控管、網路銀行、電腦主機與程式控管、密碼、資訊單位",
     r"電子銀行|網路銀行|網路安全|電腦|程式|資訊單位|密碼|電子憑證|SET|約定轉帳|約定帳戶|主機"),
    ("T01", "內部控制與法令遵循", "內部控制制度與構成要素、巴塞爾評估原則、三道防線、法令遵循單位與主管、內控聲明書、會計師查核、檢舉",
     r"內部控制|內控|法令遵循|法規遵循|法遵|聲明書|委託會計師|會計師.{0,4}(?:辦理|查核)|巴塞爾|三道防線|內部環境|構成要素|內部查核|檢舉|舞弊|生活規範"),
    ("T07", "逾期放款、催收、呆帳與債權保全", "逾放定義、資產分類與備抵、轉銷呆帳、時效、強制執行與假扣押、不良債權出售",
     r"逾期放款|逾放|催收|呆帳|授信資產|資產評估|備抵|轉銷|時效|請求權|強制執行|執行名義|假扣押|查封|拍賣|不良債權|資產管理公司|第[一二三四五]類|類資產|收回困難|應予注意|延滯|圈存|抵銷|加速條款"),
    ("T05", "授信與徵信", "授信準則（直接／間接授信）、徵信準則、擔保品與保證人、授信文件、應收帳款承購",
     r"授信|徵信|擔保品|保證人|擔保|放款|貸款|借款|應收帳款|本票|貼現|透支|鑑價|估價"),
    ("T09", "存款業務", "開戶與身分查證、各種存款、定存與可轉讓定存單、同業存款、死亡存戶、存摺、扣繳稅款",
     r"存款|開戶|存戶|存摺|存單|帳戶|印鑑|儲蓄|繼承|扣繳|利息所得|身分證|戶役政"),
    ("T10", "出納、匯兌、票據與有價證券保管", "現金與庫房、空白單據、匯兌、託收與交換票據、掛失止付、退票、有價證券保管",
     r"出納|現金|庫房|空白單據|空白|匯兌|票據|支票|匯票|託收|掛失|退票|交換|有價證券|券幣|鑰匙"),
]
OTHER = ("T99", "其他", "規則分不出主題的題目（不硬塞）")
# 法規全名本身含有關鍵字（例如實施辦法的名稱裡有「內部控制」「稽核」），比對前先拿掉，避免凡提到這部辦法就歸到同一個主題
STRIP = re.compile(r"金融控股公司及銀行業內部控制及稽核制度實施辦法|內部控制及稽核制度實施辦法")


def classify(q):
    """先只看題幹；題幹判斷不出主題時才加看正解（正解的字常把題目帶到別的主題，開發組第一輪看到的主要錯誤來源）。"""
    stem = STRIP.sub("", q["stem"])
    for text in (stem, stem + " " + STRIP.sub("", q["options"][q["answer"] - 1])):
        for code, _n, _s, pat in TOPICS:
            if re.search(pat, text):
                return code
    return OTHER[0]


def selfhash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def load():
    allq = json.loads(PACK.read_text(encoding="utf-8"))["questions"]
    split = json.loads((STUDY / "split.json").read_text(encoding="utf-8"))
    return {q["id"]: q for q in allq}, split


def frozen_hash():
    log = STUDY / "log.tsv"
    rows = [l.split("\t") for l in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    hs = [r[3] for r in rows if len(r) >= 4 and r[1] == "freeze-topics"]
    return hs[-1] if hs else None


def main(argv):
    names = {c: n for c, n, *_ in TOPICS} | {OTHER[0]: OTHER[1]}
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--dev":
        qs, split = load()
        dev = [qs[i] for i in split["dev"]]
        got = {}
        for q in dev:
            got.setdefault(classify(q), []).append(q)
        out = Path(tempfile.gettempdir()) / "certquiz-topics-dev.txt"   # 只在本機暫存，供我檢查分類明細
        with out.open("w", encoding="utf-8") as f:
            for code in [c for c, *_ in TOPICS] + [OTHER[0]]:
                for q in got.get(code, []):
                    f.write(f"{code} {names[code]}｜{q['id'][-8:]}｜{q['stem'][:70]}｜答：{q['options'][q['answer'] - 1][:30]}\n")
        for code in [c for c, *_ in TOPICS] + [OTHER[0]]:
            g = got.get(code, [])
            print(f"  {code} {names[code]:16} {len(g):4}（法規 {sum(q['subject'] == 'law' for q in g)}、實務 {sum(q['subject'] == 'gen' for q in g)}）")
        print(f"開發組 {len(dev)} 題；其他 {len(got.get(OTHER[0], []))} 題；明細：{out}")
        return 0
    if argv[0] == "--freeze":
        h = selfhash()
        with (STUDY / "log.tsv").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\tfreeze-topics\t{Path(__file__).name}\t{h}\n")
        print(f"STUDY-TOPICS FROZEN：sha256 {h[:16]}…（已記入 log.tsv）")
        return 0
    if argv[0] == "--apply":
        fh = frozen_hash()
        if fh is None:
            print("STUDY-TOPICS ABORT：規則還沒凍結（先 --freeze）")
            return 2
        if fh != selfhash():
            print("STUDY-TOPICS ABORT：規則在凍結之後被改過（雜湊不同）——要改只能作廢這一輪，見 docs/K 的自我約束")
            return 2
        qs, split = load()
        active = [q for q in qs.values() if not q.get("dupOf")]
        topics = {q["id"]: classify(q) for q in active}
        out = STUDY / "topics.json"
        out.write_text(json.dumps({"rules_sha256": fh, "names": names, "topics": topics}, ensure_ascii=False, indent=1), encoding="utf-8")
        cnt = {}
        for v in topics.values():
            cnt[v] = cnt.get(v, 0) + 1
        hold = set(split["holdout"])
        print(f"STUDY-TOPICS OK：{len(topics)} 題 → {out.relative_to(ROOT)}；其他 {cnt.get(OTHER[0], 0)} 題"
              f"（驗收組其他 {sum(1 for i, v in topics.items() if i in hold and v == OTHER[0])} 題）")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
