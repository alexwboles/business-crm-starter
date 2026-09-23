const money = new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0});
let leads=[];

async function load(){
  const response=await fetch('/api/dashboard');
  if(!response.ok) throw new Error('Dashboard could not be loaded.');
  const data=await response.json();
  leads=data.leads;
  document.querySelector('#open-count').textContent=data.open_count;
  document.querySelector('#pipeline-value').textContent=money.format(data.pipeline_value);
  document.querySelector('#followups-due').textContent=data.followups_due;
  document.querySelector('#won-value').textContent=money.format(data.won_value);
  renderStages(data.stage_counts);
  renderRows(leads);
}

function renderStages(counts){
  const max=Math.max(1,...Object.values(counts));
  document.querySelector('#stage-bars').innerHTML=Object.entries(counts).map(([stage,count])=>`
    <div class="stage"><div class="stage-top"><strong>${stage}</strong><span>${count}</span></div><div class="bar"><i style="width:${Math.max(5,count/max*100)}%"></i></div></div>`).join('');
}

function renderRows(items){
  document.querySelector('#lead-rows').innerHTML=items.map(lead=>`
    <tr>
      <td class="contact"><strong>${escapeHtml(lead.name)}</strong><span>${escapeHtml(lead.company||lead.email)}</span></td>
      <td><span class="pill">${escapeHtml(lead.stage)}</span></td>
      <td>${money.format(lead.value)}</td>
      <td><span class="pill ${lead.priority.toLowerCase()}">${escapeHtml(lead.priority)}</span></td>
      <td class="action">${escapeHtml(lead.recommended_action)}</td>
    </tr>`).join('')||'<tr><td colspan="5">No matching leads.</td></tr>';
}

function escapeHtml(value){
  return String(value).replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}

const dialog=document.querySelector('#lead-dialog');
document.querySelector('#open-form').addEventListener('click',()=>dialog.showModal());
for(const id of ['close-form','cancel-form']) document.querySelector(`#${id}`).addEventListener('click',()=>dialog.close());
document.querySelector('#search').addEventListener('input',event=>{
  const query=event.target.value.toLowerCase();
  renderRows(leads.filter(lead=>`${lead.name} ${lead.company}`.toLowerCase().includes(query)));
});
document.querySelector('#lead-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const form=new FormData(event.target);
  const payload=Object.fromEntries(form.entries());
  const response=await fetch('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const result=await response.json();
  if(!response.ok){document.querySelector('#form-error').textContent=result.error||'Lead could not be saved.';return;}
  event.target.reset(); dialog.close(); await load();
});

load().catch(error=>{document.querySelector('#lead-rows').innerHTML=`<tr><td colspan="5">${escapeHtml(error.message)}</td></tr>`;});
