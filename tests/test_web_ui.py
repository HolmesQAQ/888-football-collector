import shutil
import subprocess
import unittest
import app

class WebSelectionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed for browser script regression checks')
    def test_selection_refresh_and_open_request(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const page=fs.readFileSync(0,'utf8');
const select={value:'',children:[],replaceChildren(){this.children=[];this.value=''},appendChild(x){this.children.push(x)}};
const status={textContent:'',scrollIntoView(){}};
const context={document:{querySelector(s){if(s==='#history')return select;if(s==='#actionMessage')return status;throw Error(s)},createElement(){return {value:'',textContent:''}}}};
vm.createContext(context);
const js=page.split('<script>')[1].split('</script>')[0];
// Remove the startup polling calls only. Exercise production functions unchanged.
vm.runInContext(js.slice(0,js.lastIndexOf('setInterval(')),context);
(async()=>{
 let requests=[];context.api=async(path,args)=>{requests.push([path,args]);return path==='/api/history'?{runs:['new','old']}:{message:'opened'}};
 await context.refreshHistory('new');assert.equal(select.value,'new');
 select.value='old';await context.refreshHistory();assert.equal(select.value,'old');
 await context.openFolder('selected');assert.equal(requests.at(-1)[1].run_id,'old');assert.equal(status.textContent,'opened');
 await context.refreshHistory('new');await context.openFolder('selected');assert.equal(requests.at(-1)[1].run_id,'new');
 let pending=[];context.api=()=>new Promise(resolve=>pending.push(resolve));
 let first=context.refreshHistory('old'),second=context.refreshHistory('new');
 pending[1]({runs:['new','old']});await second;pending[0]({runs:['old']});await first;assert.equal(select.value,'new');
 context.api=async()=>({runs:[]});await context.refreshHistory();assert.equal(select.value,'');
 await context.openFolder('selected');assert(status.textContent.includes('请先选择历史记录'));
 context.api=async()=>{throw Error('permission denied')};select.value='new';await context.openFolder('selected');assert(status.textContent.includes('permission denied'));
})().catch(e=>{console.error(e);process.exitCode=1});
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=app.PAGE,text=True,encoding="utf-8",capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
