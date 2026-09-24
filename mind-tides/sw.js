const CACHE='mind-tides-shell-v2';
const SHELL=['/mind-tides/','/mind-tides/index.html','/mind-tides/manifest.webmanifest','/mind-tides/icon.svg','/mind-tides/offline.html'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('mind-tides-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET') return;
  if(event.request.mode==='navigate'){
    event.respondWith(fetch(event.request).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));return response;}).catch(()=>caches.match(event.request).then(hit=>hit||caches.match('/mind-tides/index.html')).then(hit=>hit||caches.match('/mind-tides/offline.html'))));
    return;
  }
  event.respondWith(caches.match(event.request).then(hit=>hit||fetch(event.request)));
});
