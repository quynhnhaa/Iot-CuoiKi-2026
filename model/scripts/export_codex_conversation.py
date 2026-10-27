"""Export visible user/assistant messages from a local Codex session to Markdown.

Developer instructions, reasoning, tool calls, tool outputs, and metadata are omitted.
Run this script again to refresh the snapshot while the source chat is active.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / 'model/reports/PHIEN-TRO-CHUYEN-CODEX.md'


def find_session(codex_home: Path, session_id: str) -> Path:
    matches = list((codex_home / 'sessions').rglob(f'*{session_id}.jsonl'))
    if len(matches) != 1:
        raise RuntimeError(f'Expected one session log for {session_id}, found {len(matches)}')
    return matches[0]


def export(source: Path, output: Path, session_id: str) -> int:
    timezone = ZoneInfo('Asia/Ho_Chi_Minh')
    lines = [
        '# Bản sao trò chuyện Codex',
        '',
        f'- Session ID: `{session_id}`',
        f'- Xuất lúc: {datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S %Z")}',
        '- Nội dung: lời người dùng và câu trả lời hiển thị của trợ lý đến thời điểm xuất.',
        '- Không gồm tool log, dữ liệu nội bộ hoặc trạng thái ứng dụng Codex.',
        '',
    ]
    count = 0
    seen = set()
    with source.open(encoding='utf-8') as stream:
        for raw in stream:
            event = json.loads(raw)
            if event.get('type') != 'response_item':
                continue
            message = event.get('payload') or {}
            if message.get('type') != 'message' or message.get('role') not in {'user', 'assistant'}:
                continue
            phase = message.get('phase')
            if message['role'] == 'assistant' and phase not in {'commentary', 'final_answer'}:
                continue
            identifier = message.get('id')
            if identifier in seen:
                continue
            seen.add(identifier)
            chunks = [part['text'] for part in message.get('content', [])
                      if part.get('type') in {'input_text', 'output_text'} and isinstance(part.get('text'), str)]
            if not chunks:
                continue
            metadata = message.get('internal_chat_message_metadata_passthrough') or {}
            timestamp = metadata.get('create_time')
            when = (datetime.fromtimestamp(timestamp, timezone).strftime('%Y-%m-%d %H:%M:%S')
                    if isinstance(timestamp, (int, float)) else 'không rõ giờ')
            speaker = 'Người dùng' if message['role'] == 'user' else 'Trợ lý'
            lines.extend([f'## {speaker} · {when}', '', '\n\n'.join(chunks).strip(), ''])
            count += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--session-id', default=os.environ.get('CODEX_SESSION_ID'), required=False)
    parser.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME', '~/.codex')).expanduser())
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.session_id:
        parser.error('pass --session-id or set CODEX_SESSION_ID')
    source = find_session(args.codex_home, args.session_id)
    count = export(source, args.output, args.session_id)
    print(f'Exported {count} visible messages to {args.output}')


if __name__ == '__main__':
    main()
