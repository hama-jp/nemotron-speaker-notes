# 開発と検証

変更対象に対応するテストを追加し、`python -m unittest discover -v` と
`node --check static/app.js` を実行してください。テスト用依存は
`python -m pip install -r requirements-test.txt` で導入できます。
CIはGPUやモデルを使わず、話者の時刻対応とAPIの境界を検証します。
実際の推論を変更した場合はCUDA環境で音声を解析して確認してください。

UIの変更は再生・シーク・文章編集・追従のオン／オフ・狭い画面で確認します。
録音、文字起こし、モデル重み、認証情報をコミットしないでください。
不具合報告にはOS・GPU・Python・依存バージョンと再現手順を添え、
機密の録音や個人情報を含むログを公開Issueに貼らないでください。
