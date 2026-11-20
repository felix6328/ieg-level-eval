const ws = document.getElementById('workspace');
const notice = document.getElementById('notice');
const dims = ['逻辑自洽性','趣味性','难度匹配度','可玩性'];
const titles = {overview:'总览', experiments:'实验中心', datasets:'数据集', calibration:'Judge 校准',
  triage:'分流与审核', governance:'Bad / Golden Case', reports:'回归与选型报告', experiment:'实验运行', run:'评测工作台',
  dataset:'数据集版本', report:'报告'};
const display = {REPLAY:'历史 Replay', REAL:'真实调用', MOCK:'Mock', TERRA_MODEL_REFERENCE:'Terra 模型参照',
  HISTORICAL_JUDGE:'历史 Judge', REAL_JUDGE:'在线 Judge', HUMAN:'独立人审', MODEL_ASSISTED:'模型辅助人审',
  SUCCEEDED:'成功', FAILED:'失败', PENDING:'排队中', RUNNING:'执行中', PASS:'通过', FAIL:'阻断',
  WARNING:'告警', NOT_CHECKED:'未检查', AUTO_PASS:'自动通过', AUTO_BLOCK:'自动拦截', NEEDS_HUMAN_REVIEW:'待人工复核',
  HUMAN_ACCEPT:'人审接收', HUMAN_REJECT:'人审驳回', VALID:'有效', INVALID:'需核查',
  NO_QUOTE_REQUIRED:'旧口径无需引文', NOT_RUN:'未调用', FROZEN:'已冻结', DRAFT:'草稿', VALIDATING:'待审核',
  APPROVED:'已批准', ACTIVE:'已发布', DEPRECATED:'已退役'};
let token = 0;
let timer = null;
function h(x) {
  return String(x ?? '—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function badge(value) {
  return '<span class="badge '+h(value)+'">'+h(display[value] ?? value)+'</span>';
}
const value = x => x == null ? '—' : typeof x === 'number' ? x.toLocaleString('zh-CN',{maximumFractionDigits:4}) : h(x);
const ratio = item => item?.value == null ? '—（0 样本）' : value(item.value*100)+'% <small>'+item.numerator+'/'+item.denominator+'</small>';
const json = x => '<pre>'+h(JSON.stringify(x,null,2))+'</pre>';
const expandable = (name,body) => '<details><summary>'+h(name)+'</summary>'+body+'</details>';
const link = (path,name) => '<a href="#'+h(path)+'">'+h(name)+'</a>';
function title(name,desc) {
  return '<div class="page-title"><h1>'+h(name)+'</h1><p>'+h(desc)+'</p></div>';
}
function panel(name,body,action='') {
  return '<section class="panel"><header><h2>'+h(name)+'</h2>'+action+'</header>'+body+'</section>';
}
const padded = body => '<div class="panel-body">'+body+'</div>';
const empty = text => '<div class="empty">'+h(text)+'</div>';
function table(headers,rows) {
  if (!rows.length) return empty('暂无记录。');
  return '<div class="scroll"><table><thead><tr>'+headers.map(x=>'<th>'+h(x)+'</th>').join('')+
    '</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
}
const option = (value,label) => '<option value="'+h(value)+'">'+h(label)+'</option>';
const label = (title,control) => '<label>'+h(title)+control+'</label>';
const input = (name,props='') => '<input name="'+h(name)+'" '+props+'>';
const area = (name,number=3,value='') => '<textarea name="'+h(name)+'" rows="'+number+'">'+h(value)+'</textarea>';
const select = (name,options,props='') => '<select name="'+h(name)+'" '+props+'>'+options+'</select>';
const submit = text => '<button type="submit" class="primary">'+h(text)+'</button>';
const form = (id,body,endpoint='') => '<form class="form" data-form="'+id+'" data-endpoint="'+h(endpoint)+'">'+body+'</form>';
function simple(path,text,data={},extra='') {
  return '<button type="button" data-call="'+h(path)+'" data-params="'+h(JSON.stringify(data))+'" '+extra+'>'+h(text)+'</button>';
}
function alert(message,ok=false) {
  notice.textContent=message;
  notice.classList.toggle('ok',ok);
  notice.hidden=!message;
}
async function api(path,method='GET',body) {
  const response=await fetch('/api'+path,{method,headers:body?{'Content-Type':'application/json'}:{},
    body:body?JSON.stringify(body):undefined,cache:'no-store'});
  const payload=await response.json();
  if (!response.ok) {
    const detail=payload.detail;
    throw new Error(Array.isArray(detail) ? detail.map(d=>d.msg).join('；') : (detail ?? '请求失败'));
  }
  return payload;
}
function tiles(entries) {
  return '<div class="tiles">'+entries.map(([key,count,source])=>'<article class="tile"><span>'+h(key)+'</span><strong>'+h(count)+'</strong><small>'+h(source)+'</small></article>').join('')+'</div>';
}
function expRows(items) {
  return table(['实验','模式','任务','已生成','失败','剩余'],items.map(r=>[
    link('experiment/'+r.id,r.name),badge(r.mode),value(r.total),value(r.succeeded),value(r.failed),value(r.pending+r.running)
  ]));
}
async function overview() {
  const [catalog,exps,cal,old]=await Promise.all([api('/catalog'),api('/experiments'),api('/calibration'),api('/historical')]);
  const n=catalog.versions.find(v=>v.id==='wxg24-v1')?.total ?? 0;
  return title('游戏内容评测总览','评测文字冒险关卡，对照生成配置，并追踪质量改进。')+
    tiles([['历史题库',n,'WXG 冻结数据 v1'],['实验',exps.length,'IEG 独立工作区'],
      ['Terra 模型参照',cal.references,'GPT‑6.1 Terra · high'],['独立人机配对',cal.human.independent_pairs,'真人校准样本']])+
    panel('近期实验',expRows(exps.slice(0,8)),link('experiments','打开实验中心'))+
    panel('历史质量证据',padded('<p>三组模型、分流、重写和重测从 WXG 稳定版本归档。</p>'+
      Object.entries(old).map(([key,d])=>expandable(key,json(d))).join('')))+
    '<small>真实 Provider '+(catalog.real_enabled?'已启用':'未配置')+' · 数据来自本机 SQLite</small>';
}
async function datasets() {
  const catalog=await api('/catalog');
  const items=table(['数据版本','状态','任务','来源','操作'],catalog.versions.map(v=>[
    link('dataset/'+v.id,v.name+' · V'+v.number),badge(v.state),value(v.total),h(v.source),
    v.state==='DRAFT'?simple('/datasets/'+v.id+'/freeze','冻结版本'):h(v.hash.slice(0,12))
  ]));
  const create=form('dataset',
    label('数据集',select('dataset_id',option('','新建数据集')+catalog.datasets.map(d=>option(d.id,d.name)).join('')))+
    label('新数据集名称',input('name','maxlength="120"'))+label('版本说明',input('note'))+
    label('导入文件',input('source_file','type="file" accept=".json,.jsonl"'))+
    label('任务 JSON / JSONL',area('content',10))+submit('保存新版本'));
  return title('数据集','冻结任务、划分与来源，保留可复跑版本。')+
    '<div class="grid">'+panel('数据版本',items)+panel('导入或追加版本',padded(create))+'</div>';
}
async function dataset(id) {
  const [catalog,tasks]=await Promise.all([api('/catalog'),api('/datasets/'+id+'/tasks')]);
  const version=catalog.versions.find(v=>v.id===id);
  const copy=form('dataset',input('dataset_id','type="hidden" value="'+h(version.dataset_id)+'"')+
    label('版本说明',input('note','required'))+label('任务 JSON',area('content',12,JSON.stringify(tasks,null,2)))+submit('保存为新草稿'));
  return title(version.name+' · V'+version.number,version.note)+panel('任务',
    table(['任务 ID','主题','难度','画像','划分'],tasks.map(t=>[h(t.spec_id),h(t.theme),h(t.difficulty),h(t.persona),h(t.split)])),
    badge(version.state))+panel('从此版编辑',padded(copy));
}
async function experiments() {
  const [catalog,exps]=await Promise.all([api('/catalog'),api('/experiments')]);
  const models=catalog.models.map(m=>'<label class="inline"><input type="checkbox" name="models" value="'+h(m.id)+
    '" checked> '+h(m.id+' · '+m.model.split('/').at(-1)+' · '+m.prompt_id)+'</label>').join('');
  const modes=option('REPLAY','历史 Replay')+option('MOCK','Mock 演练')+(catalog.real_enabled?option('REAL','真实调用'):'');
  const extras=label('任务 ID（留空全量）',input('task_ids','placeholder="cyber_easy, campus_hard"'))+
    '<div class="form-grid">'+label('Temperature',input('temperature','type="number" min="0" max="2" step="0.1"'))+
    label('Max tokens',input('max_tokens','type="number" min="128" max="12000"'))+
    label('替代模型（在线或 Mock）',input('model_override','maxlength="180"'))+
    label('替代 Prompt',select('prompt_override',option('','沿用配置')+catalog.prompts.map(p=>option(p.id,p.id)).join('')))+
    label('生成估算上限 CNY',input('budget_cny','type="number" min="0" max="100" step="0.01" value="0"'))+
    label('Judge 估算上限 CNY',input('judge_budget_cny','type="number" min="0" max="100" step="0.01" value="0"'))+
    label('Judge 模型（逗号分隔）',input('judge_models'))+label('语义最低分',input('min_score','type="number" min="1" max="5" value="3"'))+
    label('最低置信度',input('min_confidence','type="number" min="0" max="1" step="0.01" value="0.7"'))+
    label('维度最大分差',input('max_dimension_spread','type="number" min="0" max="4" value="1"'))+
    label('最少 Judge 数量',input('min_judges','type="number" min="2" max="3" value="2"'))+'</div>';
  const create=form('experiment',label('实验名称',input('name','required placeholder="三组模型历史对照" maxlength="120"'))+
    label('冻结数据版本',select('dataset_version',catalog.versions.filter(v=>v.state==='FROZEN').map(v=>
      option(v.id,v.name+' · V'+v.number+' · '+v.total+' 题')).join(''),'required'))+
    '<div class="form-grid">'+label('执行模式',select('mode',modes))+label('重复次数',input('repeats','type="number" min="1" max="20" value="3" required'))+
    label('种子（用于新实验）',input('seed','type="number" min="0" value="0"'))+'</div>'+
    '<fieldset><legend>对照配置</legend><div class="row">'+models+'</div></fieldset>'+
    expandable('参数、在线评审与分流策略',extras)+submit('创建并排队'));
  return title('实验中心','在冻结题库上并排运行生成模型和 Prompt。')+
    '<div class="grid">'+panel('实验列表',expRows(exps))+panel('新建实验',padded(create))+'</div>';
}
async function experiment(id,track) {
  const data=await api('/experiments/'+id);
  const active=data.runs.filter(r=>['PENDING','RUNNING'].includes(r.status)).length;
  if (active) timer=setTimeout(()=>{if(track===token) void render(false);},850);
  const counts=['SUCCEEDED','FAILED','RUNNING','PENDING'].map(s=>[display[s],data.runs.filter(r=>r.status===s).length,data.mode]);
  return title(data.name,'数据版本 '+data.dataset_version+' · '+display[data.mode])+tiles(counts)+
    panel('生成样本',table(['组别','任务','重复号','状态','产物证据','操作'],data.runs.map(r=>[
    h(r.model_config_id),link('run/'+r.id,r.task_id),value(r.sample),badge(r.status),
    h(r.source_id||r.error||r.origin),
    (r.status==='FAILED'?simple('/runs/'+r.id+'/retry','重试')+' ':'')+link('run/'+r.id,'查看')
  ])))+panel('实验快照',padded(expandable('查看模型、Prompt 与参数',json(data.config))));
}
function renderLevel(level,raw) {
  if (!level || typeof level!=='object') return '<p>生成响应未解析为关卡。</p>'+expandable('原始输出', '<pre>'+h(raw)+'</pre>');
  const choices=Array.isArray(level.choices)?level.choices:[];
  return '<h3>'+h(level.title)+'</h3><p>'+h(level.scene)+'</p><p><strong>目标</strong> '+h(level.goal)+'</p>'+
    '<ul class="choices">'+choices.map(c=>'<li><strong>'+h(c?.text)+'</strong><p>'+h(c?.outcome)+'</p><small>'+
      h(c?.result)+' · '+h(c?.next)+'</small></li>').join('')+'</ul>'+expandable('原始输出','<pre>'+h(raw)+'</pre>');
}
function judgePanel(ev) {
  const cards=ev.judges.map(j=>expandable(j.model+' · '+(display[j.source]??j.source),
    '<p>'+badge(j.status)+'</p>'+table(['维度','分数','引文或理由'],dims.map(d=>[
      h(d),value(j.scores?.[d]),h(j.dimensions?.[d]?.quote??j.dimensions?.[d]?.evidence??'—')+
      '<br><small>'+h(j.dimensions?.[d]?.reason??'')+'</small>']))+
      expandable('完整答案、原文与状态',json(j)))).join('');
  return panel('语义与模型参照',padded(cards||'<p>该输出暂无语义评审。</p>'));
}
async function run(id,track) {
  const data=await api('/runs/'+id);
  const attempt=data.attempts.at(-1);
  if (['PENDING','RUNNING'].includes(data.status)) timer=setTimeout(()=>{if(track===token) void render(false);},850);
  const base=title(data.task_id+' · '+data.model_config_id,'运行 '+id.slice(0,10)+' · '+display[data.config.mode]);
  const history=panel('请求尝试',padded(data.attempts.map(a=>expandable('尝试 '+a.number+' · '+(a.error||'请求收据'),json(a))).join('')||empty('任务尚未开始。')));
  if (!attempt?.output_id) return base+panel('状态',padded(badge(data.status)+' <p>'+h(data.error||'等待处理')+'</p>'+
    (data.status==='FAILED'?simple('/runs/'+id+'/retry','重试'):'')+' '+link('experiment/'+data.experiment_id,'返回实验')))+history;
  const out=attempt.output_id;
  const [ev,reviews,trace,rewrite]=await Promise.all([api('/outputs/'+out+'/evaluation').catch(()=>null),
    api('/outputs/'+out+'/reviews'),api('/outputs/'+out+'/trace').catch(()=>null),api('/outputs/'+out+'/rewrite')]);
  if (!ev) {
    if (track===token) timer=setTimeout(()=>{if(track===token) void render(false);},850);
    return base+panel('关卡内容',padded(renderLevel(attempt.parsed,attempt.raw)))+history;
  }
  const canReview=form('review',input('evaluation_id','type="hidden" value="'+h(ev.id)+'"')+
    label('审核人',input('reviewer','required maxlength="100"'))+
    label('评审来源',select('source',option('MODEL_ASSISTED','模型辅助、人工作出决定')+option('HUMAN','已完成独立盲评')))+
    '<label class="inline"><input name="independent" type="checkbox"> 此评分在查看模型得分前完成</label>'+
    '<div class="form-grid">'+dims.map((d,i)=>label(d,input('s'+i,'type="number" required min="1" max="5"'))).join('')+'</div>'+
    label('决定',select('decision',option('ACCEPT','接收')+option('REJECT','驳回')))+label('问题标签（逗号分隔）',input('tags'))+
    label('理由',area('note'))+submit('保存审核'),'/outputs/'+out+'/reviews');
  const current=reviews.decisions[0];
  const ruleTable=table(['规则','状态','严重程度','实际 / 预期','证据'],ev.rules.map(r=>[
    h(r.rule_id),badge(r.status),h(r.severity),h(r.actual_value)+' / '+h(r.expected_value),h(r.evidence??r.suggestion)
  ]));
  const tools=form('bad',
    label('根因类别',select('root_cause',causes()))+label('确认人（可空）',input('reviewer'))+
    label('问题说明',area('note'))+submit('新建 Bad Case'),'/outputs/'+out+'/bad-case');
  const rewriteCard=rewrite
    ? '<p>'+h(rewrite.quality)+' · '+link('run/'+rewrite.run.id,'打开重写产物')+'</p>'+
      (rewrite.after ? '<p>硬规则 '+badge(rewrite.before.hard_pass?'PASS':'FAIL')+' → '+badge(rewrite.after.hard_pass?'PASS':'FAIL')+'</p>':'')+
      expandable('重写前后、断言和费用',json(rewrite))
    : (!data.config.rewrite_for ? form('rewrite',label('修复理由',area('reason'))+submit('执行一次重写'),'/outputs/'+out+'/rewrite'):'');
  return base+'<div class="row"><p>'+link('experiment/'+data.experiment_id,'返回实验')+' · '+h(attempt.source_id||attempt.origin)+'</p>'+
    (data.config.mode!=='REAL'?simple('/outputs/'+out+'/evaluation','重新检查'):'')+'</div>'+
    '<div class="grid"><div>'+panel('关卡与需求',padded(expandable('原始需求',json(data.spec))+renderLevel(attempt.parsed,attempt.raw)))+
    panel('确定性规则',ruleTable,badge(ev.hard_pass?'PASS':'FAIL'))+judgePanel(ev)+'</div><div>'+
    panel('分流与审核',padded((current?'<p>'+badge(current.status)+' '+h(current.reason)+'</p>':'')+canReview+
    expandable('审核与分流证据',json(reviews))))+
    panel('Bad Case 与首次偏离',padded('<p>'+h(trace?.first_observable_divergence?.node??'尚无可定位的偏离')+'</p>'+
      expandable('查看 Trace',json(trace))+tools))+panel('重写闭环',padded(rewriteCard))+history+'</div></div>';
}
function causes() {
  return ['Unknown','Prompt Constraint Missing','Model Capability Limitation','Context Loss','State Inconsistency',
    'Schema Error','Game Logic Error','Evaluation Error'].map(c=>option(c,c)).join('');
}
async function calibration() {
  const c=await api('/calibration');
  const rows=Object.entries(c.model_comparisons).map(([id,row])=>[
    h(id),ratio(row.agreement),ratio(row.calibrated.agreement),value(row.calibrated.cohen_kappa),
    expandable('四维 MAE 与校准偏移',json({raw:row.mae,calibrated:row.calibrated.mae,offsets:c.offsets[id]}))
  ]);
  return title('Judge 校准','使用 Terra 模型参照比较 Judge，并检查证据、重复稳定性和样本覆盖。')+
    tiles([['Terra 参照',c.references,'LLM_JUDGE'],['开发样本',c.dev,'拟合偏移'],['任务独立留出',c.spec_disjoint_holdout,'排除 task_id 重叠'],
     ['真人独立配对',c.human.independent_pairs,c.human.status==='INSUFFICIENT'?'样本不足':'指标可用']])+
    panel('历史 Judge 与 Terra 模型参照',table(['Judge','原判定一致','校准后一致','Cohen’s κ','维度差异'],rows))+
    panel('引文有效性',padded(table(['来源','有效 / 应验','状态分布'],Object.entries(c.evidence).map(([k,v])=>[
       h(k),ratio(v),h(JSON.stringify(v.statuses))]))))+
    panel('分歧与重测',padded(expandable('跨 Judge 配对结果',json(c.judge_pairs))+
       expandable('历史重测与稳定性',json(c.historical_retest))+expandable('独立人机结果',json(c.human))));
}
async function triage() {
  const rows=await api('/triage');
  return title('分流与审核','查看优先需要策划复核的内容、触发理由和已有决定。')+
    panel('审核队列',table(['任务','配置','模式','分流','依据','操作'],rows.map(r=>[
      h(r.task_id),h(r.model_config_id),badge(r.origin),badge(r.status),h(r.reason),link('run/'+r.run_id,'评测与审核')
    ])));
}
async function governance() {
  const data=await api('/governance');
  const bad=data.bad_cases.map(b=>expandable(b.id.slice(0,8)+' · '+b.first_divergence+' · '+b.state,
    '<p>'+h(b.root_cause)+' · '+(b.confirmed?'已确认':'待确认')+' · '+h(b.note)+'</p>'+
    form('bad-edit',label('根因',select('root_cause',causes()))+label('状态',select('state',
      ['OPEN','INVESTIGATING','RESOLVED'].map(s=>option(s,s)).join('')))+
      label('审核人',input('reviewer','required'))+label('证据与理由',area('note'))+submit('更新根因'),'/bad-cases/'+b.id)+
    '<hr>'+form('golden',label('Golden 候选名称',input('title','required'))+
      label('最小化任务补丁（JSON，可选）',area('task',2,'{}'))+
      label('预期断言（JSON）',area('assertions',3,'[{"type":"hard_pass"}]'))+
      submit('生成 Golden 候选'),'/bad-cases/'+b.id+'/golden'))).join('');
  const actions={DRAFT:['validate'],VALIDATING:['approve','reject'],APPROVED:['publish'],ACTIVE:['deprecate'],DEPRECATED:[]};
  const captions={validate:'验证候选',approve:'审核通过',reject:'退回修改',publish:'发布冻结版本',deprecate:'退役'};
  const golden=data.golden_cases.map(c=>expandable(c.title+' · '+display[c.state],
    '<p>'+badge(c.state)+' '+(c.dataset_version?link('dataset/'+c.dataset_version,'打开冻结版本'):'')+'</p>'+
    (actions[c.state].length?form('gold-action',label('操作',select('action',actions[c.state].map(a=>option(a,captions[a])).join('')))+
      label('人工审核人（验证可空）',input('reviewer'))+label('备注',area('reason'))+submit('执行状态变更'),
      '/golden/'+c.id+'/action'):'')+expandable('任务、断言及审计事件',json(c)))).join('');
  return title('Bad / Golden Case','从真实运行定位偏离，将策划批准的案例沉淀到冻结题库。')+
    '<div class="grid">'+panel('Bad Case',padded(bad||'<p>可从评测工作台创建。</p>'))+
    panel('Golden 生命周期',padded(golden||'<p>从已有 Bad Case 建立候选。</p>'))+'</div>';
}
async function reports() {
  const [exps,rows]=await Promise.all([api('/experiments'),api('/reports')]);
  const expOpts=exps.map(e=>option(e.id,e.name+' · '+display[e.mode])).join('');
  return title('回归与选型报告','按可比的实验范围比较质量、时间、预算和人工复核压力。')+
    '<div class="grid">'+panel('选型对照',padded(form('decision',
      label('实验（可多选）',select('experiments',expOpts,'multiple required size="5"'))+
      label('结构通过率门槛',input('hard_floor','type="number" min="0" max="1" step="0.01" value="0.8"'))+
      label('最少评测样本',input('min_evaluation','type="number" min="1" value="12"'))+submit('生成选型报告'))))+
    panel('版本回归',padded(form('regression',label('基线实验',select('baseline',expOpts,'required'))+
      label('候选实验',select('candidate',expOpts,'required'))+submit('执行配对回归'))))+'</div>'+
    panel('已保存报告',table(['类型','创建时间','报告'],rows.map(r=>[h(r.kind),h(r.created_at),link('report/'+r.id,'打开 '+r.id.slice(0,8))])));
}
async function report(id) {
  const r=await api('/reports/'+id);
  const q=r.payload;
  const top=title(r.kind==='REGRESSION'?'版本回归':'模型选型报告','报告快照 · '+r.created_at)+
    '<p><a class="button" download="leveleval-'+h(r.id.slice(0,10))+'.json" href="/api/reports/'+h(id)+'">下载 JSON</a></p>';
  if (r.kind==='REGRESSION') return top+panel('配对与断言',padded('<p>失败率 '+ratio(q.fail_rate)+
    ' · 未配对基线 '+h(q.unpaired_baseline)+' · 未配对候选 '+h(q.unpaired_candidate)+'</p>'+
    table(['任务','配置','状态','基线','候选','断言'],q.rows.map(d=>[
      h(d.task),h(d.arm),badge(d.status),d.before_run?link('run/'+d.before_run,'查看'):'—',link('run/'+d.after_run,'查看'),h(JSON.stringify(d.assertions))
    ]))));
  const chosen=q.candidate;
  return top+panel('结构质量候选',padded(chosen?'<h3>'+h(chosen.arm)+'</h3><p>'+h(chosen.reason)+' '+h(chosen.risk)+'</p>':
    '<p>当前范围缺少可比较、达到门槛的数据。</p>'))+
    panel('配置对照',table(['实验 / 配置','生成成功','硬规则','难例','待复核','真人验收','延迟（秒）','费用估算'],q.groups.map(g=>[
      link('experiment/'+g.experiment_id,g.name+' · '+g.arm)+' '+badge(g.mode),ratio(g.metrics.generation_success),
      ratio(g.metrics.hard_pass),ratio(g.metrics.hard_difficult),ratio(g.metrics.review_rate),ratio(g.metrics.human_acceptance),
      value(g.metrics.generation_latency_s.value),value(g.metrics.estimated_generation_cost_cny.value)
    ])))+panel('完整分母、质量、效率、成本和可靠性',padded(q.groups.map(g=>
      expandable(g.name+' · '+g.arm,json(g.metrics))).join('')));
}
const routes={overview,datasets,dataset,experiments,experiment,run,calibration,triage,governance,reports,report};
async function render(clear=true) {
  clearTimeout(timer);
  const current=++token;
  const [page,id]=location.hash.slice(1).split('/');
  const name=Object.hasOwn(routes,page)?page:'overview';
  if (clear) alert('');
  document.getElementById('breadcrumb').textContent='LevelEval / '+titles[name];
  document.querySelectorAll('nav a').forEach(a=>{
    const active=a.getAttribute('href')==='#'+({experiment:'experiments',dataset:'datasets',report:'reports',run:'experiments'}[name]??name);
    if(active) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');
  });
  try {
    const html=await routes[name](id,current);
    if(current===token) ws.innerHTML=html;
  } catch(e) {
    if(current===token) ws.innerHTML=empty(e.message);
  }
}
function split(value) {
  return value ? value.split(/[,，\s]+/).map(x=>x.trim()).filter(Boolean) : [];
}
const endpointMap={dataset:'/datasets',experiment:'/experiments',decision:'/reports/decision',regression:'/reports/regression'};
ws.addEventListener('submit',async e=>{
  const formEl=e.target;
  if (!formEl.dataset.form) return;
  e.preventDefault();
  const kind=formEl.dataset.form;
  const data=new FormData(formEl);
  const get=k=>data.get(k)||'';
  const number=(k,def=null)=>get(k)===''?def:Number(get(k));
  const button=formEl.querySelector('[type="submit"]');
  button.disabled=true;
  alert('');
  try {
    let body=Object.fromEntries(data);
    if(kind==='dataset') {
      const file=data.get('source_file');
      body={name:get('name'),dataset_id:get('dataset_id')||null,note:get('note'),
        content:get('content')||(file?.size ? await file.text() : '')};
    }
    if(kind==='experiment') body={name:get('name'),dataset_version:get('dataset_version'),mode:get('mode'),
      models:data.getAll('models'),repeats:number('repeats',3),seed:number('seed',0),task_ids:split(get('task_ids')),
      temperature:number('temperature'),max_tokens:number('max_tokens'),model_override:get('model_override')||null,
      prompt_override:get('prompt_override')||null,budget_cny:number('budget_cny',0),judge_budget_cny:number('judge_budget_cny',0),
      judge_models:split(get('judge_models')),triage_policy:{min_judges:number('min_judges',2),min_score:number('min_score',3),
        min_confidence:number('min_confidence',.7),max_dimension_spread:number('max_dimension_spread',1)}};
    if(kind==='review') body={...body,independent:data.has('independent'),tags:split(get('tags')),
      scores:Object.fromEntries(dims.map((d,i)=>[d,number('s'+i)]))};
    if(kind==='golden') body={title:get('title'),task:JSON.parse(get('task')||'{}'),assertions:JSON.parse(get('assertions'))};
    if(kind==='decision') body={experiments:data.getAll('experiments'),hard_floor:number('hard_floor',.8),
      min_evaluation:number('min_evaluation',12)};
    const result=await api(formEl.dataset.endpoint||endpointMap[kind],kind==='bad-edit'?'PATCH':'POST',body);
    if(kind==='experiment') location.hash='experiment/'+result.id;
    else if(kind==='decision'||kind==='regression') location.hash='report/'+result.id;
    else if(kind==='bad') location.hash='governance';
    else if(kind==='dataset') location.hash='dataset/'+result.id;
    else if(kind==='rewrite') location.hash='run/'+result.run_id;
    else {alert('已保存。',true); await render(false);}
  } catch(e) {alert(e.message);}
  finally {button.disabled=false;}
});
ws.addEventListener('click',async e=>{
  const button=e.target.closest('[data-call]');
  if(!button) return;
  button.disabled=true;
  try {
    await api(button.dataset.call,'POST',JSON.parse(button.dataset.params));
    alert('已处理。',true);
    await render(false);
  } catch(e) {alert(e.message);}
  finally {button.disabled=false;}
});
window.addEventListener('hashchange',()=>void render());
void render();
