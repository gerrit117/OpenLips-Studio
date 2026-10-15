const {chromium} = require(process.env.PLAYWRIGHT_MODULE);
const path = require('node:path');
(async()=>{
  const browser = await chromium.launch({headless:true});
  const page = await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  try {
    await page.goto(process.env.LIBRARY_URL);
    await page.locator('#language').selectOption('de');
    await page.locator('#song-rows tr').filter({hasText:'Browser project'}).click();
    await page.locator('#edit-artist').fill('Corrected artist');
    await page.locator('#save-meta').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent==='Projekt aktualisiert');
    const catalog=await (await page.request.get(process.env.LIBRARY_URL+'/api/v1/library')).json();
    if(catalog.projects.length!==1 || catalog.projects[0].artist!=='Corrected artist') throw Error('Save created a version or lost metadata');
    await page.screenshot({path:path.resolve('tests/artifacts/library-lifecycle-desktop.png'),fullPage:true});
    page.once('dialog',dialog=>dialog.dismiss());
    await page.locator('#remove').click();
    if(await page.locator('#song-rows tr').count()!==2) throw Error('Cancelled deletion removed a song');
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('#remove').click();
    await page.waitForFunction(()=>document.querySelectorAll('#song-rows tr').length===1);
    await page.locator('#song-rows tr').filter({hasText:'Pack song'}).click();
    await page.setViewportSize({width:390,height:844});
    await page.locator('#remove-package').waitFor({state:'visible'});
    await page.screenshot({path:path.resolve('tests/artifacts/library-lifecycle-mobile.png'),fullPage:true});
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('Mobile overflow');
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('#remove-package').click();
    await page.waitForFunction(()=>document.querySelectorAll('#song-rows tr').length===0);
    if(errors.length) throw Error(errors.join('\n'));
    process.stdout.write('PASS: metadata update, cancel/delete project, delete DLC, desktop/mobile\n');
  } finally { await browser.close(); }
})().catch(error=>{process.stderr.write(String(error.stack||error));process.exit(1);});
