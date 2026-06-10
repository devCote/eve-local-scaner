import pyppeteer

async def main():
    browser = await pyppeteer.launch()
    page = await browser.newPage()
    await page.goto('https://example.com')
    print(await page.title())
    await browser.close()

if __name__ == '__main__':
    import asyncio
    asyncio.get_event_loop().run_until_complete(main())