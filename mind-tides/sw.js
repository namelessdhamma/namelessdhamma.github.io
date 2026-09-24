const CACHE='mind-tides-shell-v3';
const SCOPE='/mind-tides/';
const SHELL=[SCOPE,SCOPE+'index.html',SCOPE+'manifest.webmanifest',SCOPE+'icon.svg',SCOPE+'offline.html'];

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));
});

self.addEventListener('activate',event=>{
  event.waitUntil(
    caches.keys()
      .then(keys=>Promise.all(keys.filter(key=>key.startsWith('mind-tides-shell-')&&key!==CACHE).map(key=>caches.delete(key))))
      .then(()=>self.clients.claim())
  );
});

self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET') return;
  const url=new URL(request.url);
  if(url.origin!==self.location.origin||!url.pathname.startsWith(SCOPE)) return;

  if(request.mode==='navigate'){
    event.respondWith(
      fetch(request)
        .then(response=>{
          if(response.ok){
            const copy=response.clone();
            event.waitUntil(caches.open(CACHE).then(cache=>cache.put(request,copy)));
          }
          return response;
        })
        .catch(async()=>{
          const exact=await caches.match(request);
          return exact||await caches.match(SCOPE+'index.html')||await caches.match(SCOPE+'offline.html');
        })
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cached=>{
      if(cached) return cached;
      return fetch(request).then(response=>{
        if(!response.ok) return response;
        const copy=response.clone();
        event.waitUntil(caches.open(CACHE).then(cache=>cache.put(request,copy)));
        return response;
      });
    })
  );
});
