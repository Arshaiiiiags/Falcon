const CACHE='persian-club-shell-v4-clean-hub';
const SHELL=['/','/index.html','/style.css','/app.js','/games.js','/hokm.js','/icons.js','/i18n.js','/icon.svg','/icon-192.png','/icon-512.png','/club-art.png','/club-font.ttf','/manifest.json','/card-CA.webp','/card-C2.webp','/card-C3.webp','/card-C4.webp','/card-C5.webp','/card-C6.webp','/card-C7.webp','/card-C8.webp','/card-C9.webp','/card-C10.webp','/card-CJ.webp','/card-CQ.webp','/card-CK.webp','/card-DA.webp','/card-D2.webp','/card-D3.webp','/card-D4.webp','/card-D5.webp','/card-D6.webp','/card-D7.webp','/card-D8.webp','/card-D9.webp','/card-D10.webp','/card-DJ.webp','/card-DQ.webp','/card-DK.webp','/card-HA.webp','/card-H2.webp','/card-H3.webp','/card-H4.webp','/card-H5.webp','/card-H6.webp','/card-H7.webp','/card-H8.webp','/card-H9.webp','/card-H10.webp','/card-HJ.webp','/card-HQ.webp','/card-HK.webp','/card-SA.webp','/card-S2.webp','/card-S3.webp','/card-S4.webp','/card-S5.webp','/card-S6.webp','/card-S7.webp','/card-S8.webp','/card-S9.webp','/card-S10.webp','/card-SJ.webp','/card-SQ.webp','/card-SK.webp','/card-back-raster.webp','/table-cloth.webp','/board-wood.webp','/checker-ivory.webp','/checker-ebony.webp'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)));self.skipWaiting();});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('persian-club-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 // Private API traffic is never intercepted, persisted, or replayed.
 if(event.request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
 if(!SHELL.includes(url.pathname))return;
 event.respondWith(fetch(event.request).then(response=>{
   if(response.ok){const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(url.pathname,copy)));}
   return response;
 }).catch(()=>caches.match(url.pathname).then(cached=>cached||Response.error())));
});
