import { cp, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const destination = path.join(root, 'site/public/demo/assets');
await mkdir(destination, { recursive: true });
await cp(path.join(root, 'apps/web/viewer.js'), path.join(destination, 'viewer.js'));
await cp(path.join(root, 'apps/web/style.css'), path.join(destination, 'viewer.css'));
await cp(path.join(root, 'site/node_modules/leaflet/dist'), path.join(destination, 'leaflet'), { recursive: true });
