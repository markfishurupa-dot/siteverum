// Overlay a private, already processed survey onto the local static build.
// The source and destination must be outside the tracked demo directory.
import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const site = path.resolve(import.meta.dirname, '..');
const source = path.resolve(site, '../private-samples/real-demo');
const target = path.join(site, 'dist/demo');
const points = JSON.parse(await readFile(path.join(source, 'points.geojson'), 'utf8'));
await mkdir(path.join(target, 'data'), { recursive: true });
for (const feature of points.features) {
  const name = feature.properties.image_path;
  if (!/^images\/[0-9]{6}\.jpg$/.test(name)) throw new Error(`Unexpected image path: ${name}`);
}
await writeFile(path.join(target, 'data/points.geojson'), JSON.stringify(points));
await cp(path.join(source, 'route.geojson'), path.join(target, 'data/route.geojson'));
await cp(path.join(source, 'images'), path.join(target, 'images'), { recursive: true });
await writeFile(path.join(target, 'data/dataset.json'), JSON.stringify({
  description: 'Private preview of the SV_20260423_114721 survey, with real photographs and GPS locations.',
  defaultBasemap: 'osm'
}));
console.log(`Prepared local preview with ${points.features.length} survey photos.`);
