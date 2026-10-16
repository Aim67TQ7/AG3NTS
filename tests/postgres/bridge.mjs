import {PGlite} from '@electric-sql/pglite';
import readline from 'node:readline';
const db=new PGlite();
for await (const line of readline.createInterface({input:process.stdin})) {
 let result;
 try {const q=JSON.parse(line);result=q.exec?await db.exec(q.exec):await db.query(q.sql,q.params||[]);process.stdout.write(JSON.stringify({ok:true,result})+'\n');}
 catch(e){process.stdout.write(JSON.stringify({ok:false,error:e.message,code:e.code})+'\n');}
}
await db.close();
