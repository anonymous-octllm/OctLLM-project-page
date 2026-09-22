"""Validate the static page, manuscript abstract, and shipped interactive models.

Run with Python 3.9+; no third-party packages or source dataset are required.
"""
import hashlib
import json
import re
import struct
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.references = []
        self.duplicates = []
        self.abstract = []
        self.abstract_depth = 0
        self.abstract_count = 0
        self.paper_href = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                self.duplicates.append(attrs['id'])
            self.ids.add(attrs['id'])
        for key in ('href', 'src', 'poster', 'data-src', 'data-figure'):
            if attrs.get(key):
                self.references.append(attrs[key])
        if attrs.get('data-resource') == 'paper':
            self.paper_href = attrs.get('href')
        if self.abstract_depth:
            self.abstract_depth += 1
        elif 'abstract-copy' in attrs.get('class', '').split():
            self.abstract_depth = 1
            self.abstract_count += 1

    def handle_endtag(self, tag):
        if self.abstract_depth:
            self.abstract_depth -= 1

    def handle_data(self, data):
        if self.abstract_depth:
            self.abstract.append(data)


def read_assignment(filename, variable):
    content = (ROOT / filename).read_text()
    payload = content.split(f'window.{variable} = ', 1)[1]
    return json.loads(payload.strip().removesuffix(';'))


def validate_glb(path):
    """Check GLB framing and ensure geometry and textures are embedded."""
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError('truncated GLB header')
    magic, version, declared_size = struct.unpack_from('<4sII', data)
    if magic != b'glTF' or version != 2 or declared_size != len(data):
        raise ValueError('invalid GLB v2 header or declared length')
    chunks = []
    offset = 12
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('truncated GLB chunk header')
        size, kind = struct.unpack_from('<I4s', data, offset)
        offset += 8
        if size % 4 or offset + size > len(data):
            raise ValueError('invalid GLB chunk alignment or length')
        chunks.append((kind, data[offset:offset + size]))
        offset += size
    if [kind for kind, _ in chunks] != [b'JSON', b'BIN\x00']:
        raise ValueError('expected an embedded JSON chunk followed by a BIN chunk')
    gltf = json.loads(chunks[0][1])
    if gltf.get('asset', {}).get('version') != '2.0':
        raise ValueError('embedded glTF version is not 2.0')
    buffers = gltf.get('buffers', [])
    if len(buffers) != 1 or 'uri' in buffers[0]:
        raise ValueError('geometry must use the embedded binary buffer')
    buffer_size = buffers[0]['byteLength']
    if not 0 <= len(chunks[1][1]) - buffer_size <= 3:
        raise ValueError('binary buffer length mismatch')
    views = gltf.get('bufferViews', [])
    for view in views:
        start, size = view.get('byteOffset', 0), view['byteLength']
        if view.get('buffer', 0) != 0 or start < 0 or size < 0 or start + size > buffer_size:
            raise ValueError('buffer view exceeds the embedded buffer')
    if not gltf.get('meshes'):
        raise ValueError('no mesh geometry')
    if not gltf.get('images') or not gltf.get('textures'):
        raise ValueError('expected embedded textured generation result')
    for image in gltf['images']:
        if image.get('uri', '').startswith('data:'):
            continue
        view_index = image.get('bufferView')
        if 'uri' in image or not isinstance(view_index, int) or not 0 <= view_index < len(views):
            raise ValueError('texture is not embedded')
        if image.get('mimeType') not in ('image/png', 'image/jpeg', 'image/webp'):
            raise ValueError('unexpected embedded texture format')
    return data


def main():
    page = Document()
    page.feed((ROOT / 'index.html').read_text())
    errors = [f'Duplicate ID: {name}' for name in page.duplicates]
    references = set(page.references)
    css = (ROOT / 'styles.css').read_text()
    references.update(re.findall(r'url\([\'"]?([^\)\'\"]+)', css))
    # Include the viewer module loaded on demand and other literal JS assets.
    # Gallery data contributes only the understanding examples used by this page.
    for filename in ('script.js', 'release-config.js'):
        references.update(re.findall(r'''["']((?:\./)?(?:assets/|vendor/)[^"'`${}\s]+)["']''', (ROOT / filename).read_text()))

    expected_abstract = ' '.join((ROOT / 'scripts/paper-abstract.txt').read_text().split())
    actual_abstract = ' '.join(''.join(page.abstract).split())
    if page.abstract_count != 1 or actual_abstract != expected_abstract:
        errors.append('Abstract must match scripts/paper-abstract.txt exactly after whitespace normalization')
    if len(expected_abstract.split()) != 203:
        errors.append('Expected the 203-word manuscript abstract fixture')
    if page.paper_href != 'paper/iclr2027_conference.pdf':
        errors.append('Default paper link must reference paper/iclr2027_conference.pdf')
    release = (ROOT / 'release-config.js').read_text()
    paper_config = re.search(r'\bpaper\s*:\s*["\']([^"\']*)["\']', release)
    if not paper_config or paper_config.group(1) != 'paper/iclr2027_conference.pdf':
        errors.append('Default release paper must reference paper/iclr2027_conference.pdf')

    models = read_assignment('model-data.js', 'MODEL_ASSETS')
    if not isinstance(models, list):
        raise SystemExit('MODEL_ASSETS must be a flat JSON array')
    if Counter(asset.get('conditionType') for asset in models) != {'image': 6, 'text': 6}:
        errors.append('Expected six image-conditioned and six text-conditioned 3D assets')
    model_ids = [asset.get('id') for asset in models]
    if len(set(model_ids)) != len(model_ids):
        errors.append('Model IDs must be unique')
    manifest = json.loads((ROOT / 'assets/models/manifest.json').read_text())
    provenance = {asset['id']: asset for asset in manifest['assets']}
    if len(provenance) != len(manifest['assets']) or set(provenance) != set(model_ids):
        errors.append('Model data and provenance manifest must contain the same unique assets')
    for asset in models:
        label = asset.get('id', '(missing ID)')
        for field in ('id', 'name', 'conditionType', 'src', 'poster', 'assetId'):
            if not asset.get(field):
                errors.append(f'{label}: missing {field}')
        if not re.fullmatch(r'[0-9a-f]{64}', asset.get('assetId', '')):
            errors.append(f'{label}: invalid source asset ID')
        if asset.get('conditionType') == 'image' and not asset.get('input'):
            errors.append(f'{label}: missing condition image')
        if asset.get('conditionType') == 'text' and not asset.get('prompt'):
            errors.append(f'{label}: missing verbatim text prompt')
        for field in ('src', 'poster', 'input'):
            if asset.get(field):
                references.add(asset[field])
        source = provenance.get(label, {})
        for field in ('assetId', 'conditionType', 'src', 'poster', 'input', 'prompt'):
            if asset.get(field) != source.get(field):
                errors.append(f'{label}: {field} differs from source manifest')
        try:
            model_path = ROOT / asset['src']
            if model_path.suffix != '.glb':
                raise ValueError('model source must be a GLB file')
            data = validate_glb(model_path)
            if len(data) != source.get('glbBytes') or hashlib.sha256(data).hexdigest() != source.get('sha256'):
                raise ValueError('model size or SHA-256 differs from source manifest')
        except (OSError, KeyError, ValueError, struct.error) as exc:
            errors.append(f'{label}: {exc}')

    gallery = read_assignment('gallery-data.js', 'OCTLLM_GALLERY')
    for item in gallery.get('understanding', []):
        references.update(item['images'])
    for ref in references:
        url = urlsplit(ref)
        if url.scheme or url.netloc:
            continue
        if not url.path and url.fragment:
            if url.fragment not in page.ids:
                errors.append(f'Missing anchor: {ref}')
            continue
        path = ROOT / unquote(url.path)
        if not path.is_file():
            errors.append(f'Missing file: {ref}')
        elif path.stat().st_size == 0:
            errors.append(f'Empty file: {ref}')
        else:
            with path.open('rb') as stream:
                header = stream.read(12)
            if path.suffix == '.webp' and (header[:4] != b'RIFF' or header[8:] != b'WEBP'):
                errors.append(f'Invalid WebP: {ref}')
            elif path.suffix == '.woff2' and header[:4] != b'wOF2':
                errors.append(f'Invalid WOFF2 font: {ref}')
            elif path.suffix == '.pdf' and not header.startswith(b'%PDF-'):
                errors.append(f'Invalid PDF: {ref}')
    assets = [path for path in (ROOT / 'assets').rglob('*') if path.is_file()]
    errors.extend(f'Large asset: {path.relative_to(ROOT)}' for path in assets if path.stat().st_size > 95 * 1024 * 1024)
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'OK: {len(references)} references and anchors; {len(models)} interactive textured GLBs; exact 203-word paper abstract.')
    print(f'Assets: {sum(path.stat().st_size for path in assets) / 1024**2:.1f} MiB.')


if __name__ == '__main__':
    main()
