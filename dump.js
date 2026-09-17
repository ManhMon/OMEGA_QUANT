const http = require(http); http.createServer((req, res) => { let b=`; req.on(data, c=>b+=c); req.on(end, ()=>{ console.log(b); res.writeHead(200); res.end({}  ); }); }).listen(8888);
