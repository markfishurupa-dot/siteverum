// Overlay a processed survey onto the separate, ignored real-preview build.
import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const site = path.resolve(import.meta.dirname, '..');
const source = path.resolve(site, '../private-samples/real-demo');
const target = path.resolve(site, '../private-samples/real-demo-site/demo');
const points = JSON.parse(await readFile(path.join(source, 'points.geojson'), 'utf8'));
if (!points.features.length) throw new Error('The survey contains no photo points.');
await mkdir(path.join(target, 'data'), { recursive: true });
await mkdir(path.join(target, 'images'), { recursive: true });
for (const feature of points.features) {
  const name = feature.properties.image_path;
  if (!/^images\/[0-9]{6}\.jpg$/.test(name)) throw new Error(`Unexpected image path: ${name}`);
  await cp(path.join(source, name), path.join(target, name));
}
await writeFile(path.join(target, 'data/points.geojson'), JSON.stringify(points));
await cp(path.join(source, 'route.geojson'), path.join(target, 'data/route.geojson'));
await writeFile(path.join(target, 'data/dataset.json'), JSON.stringify({
  description: 'Private preview of the SV_20260423_114721 survey, with real photographs and GPS locations.',
  defaultBasemap: 'osm'
}));
console.log(`Prepared local preview with ${points.features.length} survey photos.`);
