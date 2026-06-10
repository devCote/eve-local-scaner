from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from tqdm import tqdm


DAYS_BACK = 40
BASE_URL = "https://data.everef.net/killmails/{year}/killmails-{date}.tar.bz2"


def download_file(url: str, output_path: Path) -> bool:
    temp_path = output_path.with_suffix(output_path.suffix + ".part")

    try:
        with requests.get(url, stream=True, timeout=60) as response:
            if response.status_code == 404:
                print(f"[SKIP] Not found: {url}")
                return False

            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            with open(temp_path, "wb") as file, tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=output_path.name,
                ncols=100,
            ) as progress:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file.write(chunk)
                        progress.update(len(chunk))

            temp_path.replace(output_path)
            print(f"[OK] Downloaded: {output_path.name}")
            return True

    except Exception as e:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

        print(f"[ERROR] {url}")
        print(f"        {e}")
        return False


def main():
    root_dir = Path(__file__).resolve().parent
    killmails_dir = root_dir / "killmails"
    killmails_dir.mkdir(exist_ok=True)

    today = datetime.now(timezone.utc).date()

    print(f"Saving archives to: {killmails_dir}")
    print(f"Downloading last {DAYS_BACK} days...\n")

    downloaded = 0
    skipped_existing = 0
    failed = 0

    for i in range(DAYS_BACK):
        day = today - timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        year = day.strftime("%Y")

        filename = f"killmails-{date_str}.tar.bz2"
        output_path = killmails_dir / filename
        url = BASE_URL.format(year=year, date=date_str)

        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"[EXISTS] {filename}")
            skipped_existing += 1
            continue

        success = download_file(url, output_path)

        if success:
            downloaded += 1
        else:
            failed += 1

    print("\nDone.")
    print(f"Downloaded: {downloaded}")
    print(f"Already exists: {skipped_existing}")
    print(f"Failed / not found: {failed}")


if __name__ == "__main__":
    main()