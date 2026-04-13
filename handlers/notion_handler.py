import os
from datetime import datetime
from notion_client import AsyncClient

client = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")


async def save_to_notion(title: str, content: str, work_type: str, input_text: str) -> str:
    """Notionデータベースにページを作成して保存"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # コンテンツをブロックに変換（Markdown → Notion blocks）
    blocks = markdown_to_blocks(content)

    response = await client.pages.create(
        parent={"database_id": DATABASE_ID},
        properties={
            "Name": {
                "title": [{"text": {"content": f"[{work_type}] {title}"}}]
            },
            "作業タイプ": {
                "select": {"name": work_type}
            },
            "作成日時": {
                "date": {"start": datetime.now().isoformat()}
            },
            "入力内容": {
                "rich_text": [{"text": {"content": input_text[:2000]}}]
            },
        },
        children=blocks,
    )

    return response["url"]


def markdown_to_blocks(text: str) -> list:
    """MarkdownテキストをNotionブロックリストに変換"""
    blocks = []
    lines = text.split("\n")

    for line in lines:
        if not line.strip():
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}})
        elif line.startswith("# "):
            blocks.append({
                "object": "block", "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}
            })
        elif line.startswith("## "):
            blocks.append({
                "object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]}
            })
        elif line.startswith("### "):
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]}
            })
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}
            })
        elif line.startswith("```"):
            pass  # コードブロックは簡略化
        else:
            if line.strip():
                blocks.append({
                    "object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}
                })

    # Notionは100ブロックまでなので制限
    return blocks[:100]
