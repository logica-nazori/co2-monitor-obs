# 🌿 CO2モニター for OBS

配信中のCO2濃度・温度・湿度をOBS画面にリアルタイム表示するツールです。  
SwitchBot CO2センサー（MeterPro CO2）からBluetooth経由で直接データを取得します。

## ✨ できること

- 📊 CO2濃度をOBS画面にリアルタイム表示（色分け表示あり）
- 🌡 温度・💧湿度も同時表示＆ファイル出力
- ⚠️ CO2 / 温度 / 湿度の各アラート（個別ON/OFF・閾値・文言カスタマイズ可能）
- 🔍 BLEデバイス自動スキャン・選択
- 💾 設定の自動保存
- exe一発起動（Python不要）

## 📦 ダウンロード

**BOOTH（無料）**: https://nazori-logica.booth.pm/items/8031762

> 100円のお布施版もありますが、内容は完全に同じです 🙏

## 📋 必要なもの

- Windows 10/11（Bluetooth搭載）
- [SwitchBot CO2センサー](https://www.switchbot.jp/products/switchbot-meter-pro-co2)
- OBS Studio
- ※ SwitchBotハブミニは**不要**です

## 🛠 使い方

### exeで使う場合（推奨）

1. BOOTHから `CO2Monitor.exe` をダウンロード
2. ダブルクリックで起動
3. 「🔍 検索」でセンサーを選択 → モニタリング開始
4. OBSで「テキスト (GDI+)」→「ファイルからの読み取り」→ テキストファイルを指定

### 出力ファイル

| ファイル | 内容 | 例 |
|---|---|---|
| `co2_level.txt` | CO2濃度 | `CO2: 650 ppm` |
| `temperature.txt` | 温度 | `24.5°C` |
| `humidity.txt` | 湿度 | `45%` |
| `alert.txt` | アラート | `⚠ CO2が高いです！換気してください！` |

### ソースから実行する場合

```bash
# 仮想環境を作成
python -m venv venv

# 依存ライブラリをインストール
pip install -r requirements.txt

# GUI版を起動
python co2_monitor_gui.py

# CLI版を起動
python co2_monitor.py
```

## 💡 Tips

- CO2センサーのボタンを長押しするとBluetooth待機状態になり、検出されやすくなります
- USB-C給電で常時使用すると、バッテリー駆動より更新頻度が上がります（毎秒 vs 30秒）

## 📊 CO2濃度の目安

| 濃度 | 状態 |
|---|---|
| 400 ppm以下 | 屋外レベル（非常に良好） |
| 400～600 ppm | 良好 |
| 600～1000 ppm | やや高め（長時間で眠気の原因に） |
| 1000～2000 ppm | 換気推奨（集中力低下） |
| 2000 ppm以上 | 即座に換気が必要 |

## ⚠ 注意事項

- 本ツールはSwitchBot社の公式ツールではありません
- Windows Defender等のアンチウイルスに誤検知される場合があります。ソースコードは本リポジトリで全公開しています
- `.env` ファイルにはAPI認証情報が含まれるため、公開しないでください

## ライセンス

MIT License
