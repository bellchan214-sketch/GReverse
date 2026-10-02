import argparse
import json
import os
import re
import tempfile
from urllib.parse import urlparse

import requests


ALLOWED_CONTENT_TYPES = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'video/mp4',
    'video/quicktime',
}
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
CHUNK_SIZE = 8192


def sanitize_filename(filename):
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename).strip()
    if not sanitized or sanitized.startswith('.'):
        sanitized = '_' + sanitized
    return sanitized[:180]


def is_http_url(url):
    try:
        return urlparse(url).scheme.lower() in {'http', 'https'}
    except (TypeError, ValueError):
        return False


def download_item(session, item, output_dir, max_bytes, timeout):
    if not isinstance(item, dict):
        return 'Skipped: catalog entry is not an object.'

    media_url = item.get('url')
    filename = item.get('filename')
    if not isinstance(media_url, str) or not is_http_url(media_url):
        return 'Skipped: missing or invalid media URL.'
    if not isinstance(filename, str) or not filename.strip():
        return 'Skipped: missing filename.'

    safe_filename = sanitize_filename(filename)
    output_path = os.path.join(output_dir, safe_filename)
    if os.path.exists(output_path):
        return f"Skipped '{safe_filename}': file already exists."

    temporary_path = None
    try:
        with session.get(media_url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            content_type = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
            if content_type not in ALLOWED_CONTENT_TYPES:
                return f"Skipped '{safe_filename}': unsupported content type '{content_type}'."

            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > max_bytes:
                return f"Skipped '{safe_filename}': file exceeds the {max_bytes}-byte limit."

            with tempfile.NamedTemporaryFile(dir=output_dir, delete=False) as output_file:
                temporary_path = output_file.name
                downloaded = 0
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        return f"Skipped '{safe_filename}': file exceeds the {max_bytes}-byte limit."
                    output_file.write(chunk)

        if downloaded == 0:
            return f"Skipped '{safe_filename}': response was empty."
        os.replace(temporary_path, output_path)
        temporary_path = None
        return f"Downloaded '{safe_filename}'."
    except (requests.exceptions.RequestException, ValueError, OSError) as error:
        return f"Error downloading '{safe_filename}': {error}"
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def process_sources(source_urls, output_dir, max_bytes, timeout):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Target directory: '{output_dir}'")

    with requests.Session() as session:
        for source_url in source_urls:
            print(f"\nProcessing media source: {source_url}")
            if not is_http_url(source_url):
                print('Skipped: source must use HTTP or HTTPS.')
                continue

            try:
                response = session.get(source_url, timeout=timeout)
                response.raise_for_status()
                media_items = response.json()
                if not isinstance(media_items, list):
                    print('Skipped: source response is not a JSON list.')
                    continue

                print(f'Found {len(media_items)} catalog entries.')
                for item in media_items:
                    print('  ' + download_item(session, item, output_dir, max_bytes, timeout))
            except (requests.exceptions.RequestException, ValueError, json.JSONDecodeError) as error:
                print(f'Error processing source: {error}')


def main():
    parser = argparse.ArgumentParser(description='Download allowed media from JSON catalog endpoints.')
    parser.add_argument('--source', action='append', required=True, help='HTTP(S) URL returning a JSON list of {"url", "filename"} entries. Repeat for multiple sources.')
    parser.add_argument('--output-dir', default='downloaded_media', help='Directory for downloaded files.')
    parser.add_argument('--max-bytes', type=int, default=DEFAULT_MAX_BYTES, help='Maximum size of each downloaded file.')
    parser.add_argument('--timeout', type=float, default=15, help='Request timeout in seconds.')
    args = parser.parse_args()

    if args.max_bytes <= 0 or args.timeout <= 0:
        parser.error('--max-bytes and --timeout must be greater than zero.')
    process_sources(args.source, args.output_dir, args.max_bytes, args.timeout)


if __name__ == '__main__':
    main()