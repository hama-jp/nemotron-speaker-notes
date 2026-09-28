# 話者ノート / Nemotron Speaker Notes

日本語の会議録画を、話者付きの文字起こしとタイムラインで確認するローカルWebツールです。
**Nemotron 3 Diarization**で「いつ・誰の声か」を推定し、**Whisper large-v3-turbo**で文章にします。
録音を先に解析し、その結果を再生に同期して表示します。

## できること

- 動画・音声をアップロードし、最大8話者の発話区間を色分け。
- 日本語の文字起こし。再生中の文章を話者色で強調し、自動スクロール。
- 文章・タイムラインをクリックして原音へ移動。追従はオフにもできます。
- 話者名と文章の修正。動画の人物を手動で囲み、推定話者に対応付け。
- JSON・SRT・テキストを書き出し。収録向けの「実演表示」。

音声を外部のAIサービスへ送信しません。初回のパッケージ・モデル取得には通信が必要です。
顔認識・人物追跡は行いません。枠は手動設定で、画面配置が変われば見直してください。

## セットアップ

Linux / WSL2 と NVIDIA CUDA GPU を前提とします。動作確認環境は
RTX 3090（24GB）、WSL2、Python 3.14.3、PyTorch 2.14.0+cu130です。
CPU・macOS・Windowsネイティブでのモデル推論は未検証です。24GBが必須という意味ではありません。
Python 3.12以降を想定していますが、モデル推論の確認は上記環境のみです。

### GPUメモリと保存容量

**導入時のVRAM目安は8GB以上**です。これは以下の観測値に余裕を加えた目安で、
8GB GPUでの動作保証や、実測した最小容量ではありません。他のGPUアプリも使う場合は、その使用量を別途確保してください。

| 対象 | 確認した容量・条件 |
| --- | --- |
| Nemotron＋Whisper turbo | PyTorch確保ピーク約5.5GiB、使用中テンソルのピーク約5.0GiB |
| 計測条件 | RTX 3090 / 日本語録画約5分 / 1件ずつ処理 / Nemotron float32 / Whisper fp16推論 / 両モデル常駐 |
| モデルの保存容量 | 合計約2.0GB（Nemotron約0.40GB＋Whisper約1.62GB） |
| その他のディスク容量 | Python・CUDA依存環境で数GB、さらに入力・再生用動画・結果の保存領域が必要 |

PyTorchの値にはCUDAコンテキストや他アプリの使用量を含みません。録音の条件によっても変わります。
[Whisper公式](https://github.com/openai/whisper#available-models-and-languages)のturbo単体の目安は約6GBです。
このツールではNemotronを残したままWhisperを使うため、ツール全体を計測しています。
最初の解析後はモデルをGPUに保持し、サーバー終了時に解放します。
初期導入には20GB程度以上の空きを用意し、録画の保存量に合わせて増やしてください。

### インストール

```bash
git clone https://github.com/hama-jp/nemotron-speaker-notes.git
cd nemotron-speaker-notes
sudo apt-get update
sudo apt-get install -y ffmpeg libsndfile1 git
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

[PyTorch公式のインストール手順](https://pytorch.org/get-started/locally/)で、
GPUドライバーに対応するCUDA版を先にインストールしてください。
今回の確認環境に合わせる場合は以下です。

```bash
python -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install -r requirements.txt
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
python prepare_models.py
bash start.sh
```

CUDAの確認で `True` が出ることを確認します。ブラウザで **http://localhost:18763** を開いてください。
終了はターミナルで `Ctrl+C`。WSLでは仮想環境をLinux側のファイルシステムに置くと導入がスムーズです。

モデルはNemotronのrevisionとTransformersのcommitを固定しています。
`prepare_models.py` はNemotronとWhisperを取得します。話者推定だけなら
`python prepare_models.py --diarization-only` とし、画面の「日本語を文字起こし」をオフにします。
Whisperはキャッシュにない場合、解析時にも取得を試みます。

## 使い方

1. 「日本語を文字起こし」を選び、「動画・音声を開く」からファイルを選択。
2. 完了後に再生。話者カード・字幕・文章の強調が再生時刻に連動します。
3. 必要に応じて名前・文章を編集。人物枠は「枠を指定」からドラッグします。
4. JSON・SRT・テキストを保存。「実演表示」はEscで戻ります。

名前・枠・文章の編集は、そのブラウザのlocalStorageに保存します。
別端末とは共有しません。生の推論結果はサーバーに保持し、JSON書き出しには修正前の文章も含めます。
ブラウザの保存データを消す前に書き出してください。

## 待ち時間を減らす構成

- 互換性のあるH.264動画（8bit 4:2:0・最大1920×1080）は映像を再圧縮せずMP4へ格納。AAC音声もコピーし、それ以外の音声だけAACへ変換します。
- その他の動画はH.264へ変換。その準備を音声の話者推定・文字起こしと並行して進めます。動画変換に失敗しても、解析に成功していれば音声で結果を確認できます。
- NemotronとWhisperは最初の解析後に再利用し、次のファイルで読み直しません。16kHz音声配列も両方の解析で共有します。
- GPU解析は1件ずつ進め、複数録画の同時推論によるVRAM不足を避けます。

確認例：RTX 3090で同じ約5分の日本語録画を2件直列処理したところ、初回48.0秒、
2回目15.5秒でした（アップロード時間を除く）。初回にはWhisperの読み込み約26.5秒を含みます。
同じ入力に対する話者区間・文字起こし・表示用データは初版と一致しました。
これは共有デスクトップ上の1回ずつの観測例で、一般的な速度倍率・所要時間の保証ではありません。
処理段階ごとの診断時間は`data/<job-id>/job.json`の`timings`に保存します。動画準備と解析が重なるため、各時間の単純合計は総時間になりません。

## 制限とデータ保存

入力は最大1時間・2GB。mp4 / webm / mov / mkv / wav / mp3 / m4a / flac / ogg / opusを受け付けます。
これは受付上限で、1時間の全条件で動作を保証するものではありません。
処理は1件ずつ、同時受付は3件まで。保存先の空きが8GB未満なら受付を停止します。
動画はブラウザ用MP4を別途保存するため、入力と結果の両方の保存容量が必要です。

- 話者IDはファイル内だけの識別子です。人物の身元や別ファイルとの一致は推定しません。
- 単語時刻と発話区間の重なりから話者を割り当てます。対応が弱い、または複数候補がある箇所は「要確認」です。
- 同時発話の声を分離して双方の文章を復元する機能ではありません。固有名詞などは原音で確認してください。
- 発話スコアはモデル出力です。認識の正解率ではありません。
- ライブ文字起こしではありません。Nemotronの解析後にWhisperを実行します。

メディア・結果・エラーログは `data/<job-id>/` に保存し、自動削除しません。
削除するときはサーバーを停止し、対象ジョブのディレクトリを削除してください。
再起動時に中断ジョブはエラー表示となり、自動再実行しません。

| 環境変数 | 既定値・用途 |
| --- | --- |
| `PORT` | `18763`。start.shの待受ポート |
| `DIARIZATION_DATA` | リポジトリ内の `data/` |
| `HF_HOME` | Hugging Face標準のキャッシュ先。モデル取得と起動時に同じ値を使用 |
| `WHISPER_CACHE` | リポジトリ内の `.cache/whisper/` |

認証機能はありません。起動スクリプトは `127.0.0.1` のみにバインドします。
他のPCからはSSHトンネルを使えます。接続元PCで以下を実行し、同じlocalhost URLを開きます。

```bash
ssh -N -L 18763:127.0.0.1:18763 USER@GPU_HOST
```

## 検証

録画・音声・実際の会議の文字起こし・モデル重みは同梱しません。
導入直後は空の画面から、自分のファイルを選んで利用できます。

RTX 3090上で、日本語会議の冒頭5分を解析し、4つの話者ID・64区間・55行の文章が生成されることを確認しました。
正解ラベルとの精度評価ではありません。話者対応や文字起こしには誤りもあります。
動画・音声の受付、名前と文章の編集、書き出し、再生位置の強調・追従、狭い画面での表示を検証しています。

```bash
python -m pip install -r requirements-test.txt
python -m unittest discover -v
node --check static/app.js
```

CIではGPU不要の単体・APIテストを実行します。開発手順は [CONTRIBUTING.md](CONTRIBUTING.md)。

## 困ったとき

- **CUDAを利用できない**：NVIDIAドライバー、WSLのGPU連携、CUDA版PyTorchを確認してください。
- **モデルが見つからない**：起動と同じ仮想環境・`HF_HOME` で `python prepare_models.py` を実行してください。
- **Nemotronのクラスを読み込めない**：`requirements.txt` の固定commitのTransformersを使用してください。
- **GPUメモリ不足**：自分が管理するほかのGPU処理を停止してから、短いファイルで試してください。
- **文字起こしだけ失敗**：話者推定結果は残ります。ジョブの `asr-error.log` を確認してください。
- **動画変換失敗**：FFmpegの導入、入力の音声トラックとコーデックを確認してください。

## ライセンス・クレジット

このアプリのコードは [MIT License](LICENSE)。NVIDIAの公式製品ではありません。
使用するモデル・ライブラリ・入力素材の条件はそれぞれ別です。

- [NVIDIA Nemotron-3-Diarization](https://huggingface.co/nvidia/Nemotron-3-Diarization)：OpenMDW-1.1。使用revision `f667ed73aee57d40cc39428eb768b4fd87a0a29e`。
- [OpenAI Whisper](https://github.com/openai/whisper)：MIT。large-v3-turboを使用。
- [Hugging Face Transformers](https://github.com/huggingface/transformers)：Apache-2.0。使用commit `07338b6c74a578868368e6e549dea83414e4b8cb`。
