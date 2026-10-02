import argparse
import hashlib
import os
import sys

try:
	from skimage.color import rgb2gray
	from skimage.io import imread
	from skimage.metrics import structural_similarity
	from skimage.transform import resize
	from skimage.util import img_as_float
except ImportError:
	print('Missing dependencies. Install them with: python3 -m pip install scikit-image numpy', file=sys.stderr)
	sys.exit(1)


IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff')


def list_files(target_dir):
	paths = []
	for root, _, filenames in os.walk(target_dir):
		paths.extend(os.path.join(root, filename) for filename in filenames)
	return sorted(paths)


def find_exact_duplicates(paths):
	hashes = {}
	duplicates = []
	for path in paths:
		digest = hashlib.sha256()
		try:
			with open(path, 'rb') as source_file:
				for chunk in iter(lambda: source_file.read(8192), b''):
					digest.update(chunk)
		except OSError as error:
			print(f'Could not hash {path}: {error}', file=sys.stderr)
			continue

		file_hash = digest.hexdigest()
		if file_hash in hashes:
			duplicates.append((path, hashes[file_hash]))
		else:
			hashes[file_hash] = path
	return duplicates


def preprocess_image(path, target_size=(256, 256)):
	try:
		image = img_as_float(imread(path))
		if image.ndim == 3:
			image = rgb2gray(image[:, :, :3]) if image.shape[2] >= 3 else image[:, :, 0]
		if image.ndim != 2:
			return None
		return resize(image, target_size, anti_aliasing=True)
	except (OSError, ValueError, TypeError):
		return None


def find_visual_matches(target_dir, query_path=None, threshold=0.45):
	paths = [path for path in list_files(target_dir) if path.lower().endswith(IMAGE_EXTENSIONS)]
	features = {path: preprocess_image(path) for path in paths}
	matches = []

	if query_path:
		query_image = preprocess_image(query_path)
		if query_image is None:
			raise ValueError(f'Could not read query image: {query_path}')
		for path, image in features.items():
			if image is None or os.path.abspath(path) == os.path.abspath(query_path):
				continue
			score = structural_similarity(query_image, image, data_range=1.0)
			if score >= threshold:
				matches.append((query_path, path, score))
	else:
		usable = [(path, image) for path, image in features.items() if image is not None]
		for index, (first_path, first_image) in enumerate(usable):
			for second_path, second_image in usable[index + 1:]:
				score = structural_similarity(first_image, second_image, data_range=1.0)
				if score >= threshold:
					matches.append((first_path, second_path, score))

	return sorted(matches, key=lambda match: match[2], reverse=True)


def main():
	parser = argparse.ArgumentParser(description='Find exact and visually similar local images.')
	parser.add_argument('--target-dir', default='images', help='Directory to scan (default: images).')
	parser.add_argument('--query', help='Optional local image to compare against the target directory.')
	parser.add_argument('--threshold', type=float, default=0.45, help='SSIM threshold from 0 to 1 (default: 0.45).')
	args = parser.parse_args()

	if not os.path.isdir(args.target_dir):
		parser.error(f'target directory does not exist: {args.target_dir}')
	if args.query and not os.path.isfile(args.query):
		parser.error(f'query image does not exist: {args.query}')
	if not 0 <= args.threshold <= 1:
		parser.error('--threshold must be between 0 and 1')

	duplicates = find_exact_duplicates(list_files(args.target_dir))
	print(f'Exact duplicate pairs: {len(duplicates)}')
	for duplicate, original in duplicates:
		print(f'  {duplicate} is identical to {original}')

	matches = find_visual_matches(args.target_dir, args.query, args.threshold)
	print(f'Visual matches at or above {args.threshold:.0%}: {len(matches)}')
	for first_path, second_path, score in matches:
		print(f'  {score:.1%}: {first_path} <-> {second_path}')


if __name__ == '__main__':
	main()
