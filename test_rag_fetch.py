import asyncio
import traceback
import sys

# 必須環境変数とパスの追加
sys.path.append("/app/backend")

from open_webui.retrieval.web.utils import SafeWebBaseLoader

async def main():
    url = 'https://www.data.jma.go.jp/multi/yoho/yoho_detail.html?code=130010&lang=en'
    print(f"Testing URL fetch for: {url}")
    loader = SafeWebBaseLoader(web_paths=[url])
    try:
        docs = await loader.aload()
        print('SUCCESS: fetched', len(docs), 'documents')
        if docs:
            print('Content length:', len(docs[0].page_content))
            print('Content excerpt:', docs[0].page_content[:200])
    except Exception as e:
        print('FAILED with exception:')
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
