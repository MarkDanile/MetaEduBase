<template>
  <div class="p-6">
    <PageHeader
      title="Skill 服务"
      subtitle="注册与管理声明式 SOP 模板（sop_template 只填声明式 YAML，绝不填 secret）"
    >
      <template #extra>
        <button
          v-if="isAdmin"
          class="ui-btn ui-btn-primary"
          data-testid="register-btn"
          @click="openCreateModal"
        >
          <Plus :size="16" /> 注册 Skill
        </button>
      </template>
    </PageHeader>

    <div class="mt-4">
      <!-- code 筛选（同 code 多版本查看） -->
      <div v-if="!loading && skills.length > 0" class="filter-bar">
        <label class="filter-label">
          <Filter :size="13" class="text-[var(--color-ink-tertiary)]" />
          <span>按 code 筛选版本</span>
        </label>
        <select
          v-model="codeFilter"
          class="ui-input filter-select"
          data-testid="code-filter"
        >
          <option value="">全部（{{ skills.length }}）</option>
          <option v-for="c in distinctCodes" :key="c" :value="c">{{ c }}</option>
        </select>
        <span v-if="codeFilter" class="filter-count text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
          {{ filteredSkills.length }} 个版本
        </span>
      </div>

      <LoadingSpinner v-if="loading" text="加载 Skill..." />
      <EmptyState
        v-else-if="skills.length === 0"
        title="暂无 Skill"
        hint="点击右上角「注册 Skill」导入第一个声明式 SOP 模板"
      />
      <div v-else class="skill-container">
        <!-- Header -->
        <div class="list-header">
          <div class="col-code">code</div>
          <div class="col-version">version</div>
          <div class="col-name">名称</div>
          <div class="col-enabled">状态</div>
          <div class="col-date">创建时间</div>
          <div class="col-ops">操作</div>
        </div>

        <!-- Rows -->
        <div
          v-for="skill in filteredSkills"
          :key="skill.id"
          class="list-row"
          data-testid="skill-row"
        >
          <div class="col-code">
            <span class="row-code">{{ skill.code }}</span>
          </div>
          <div class="col-version">
            <span class="row-version" data-testid="skill-version">{{ skill.version }}</span>
          </div>
          <div class="col-name">
            <span class="row-name">{{ skill.name }}</span>
            <span
              v-if="skill.source_ref"
              class="ui-tag-blue text-[var(--text-micro)] ml-2"
              :title="`来源: ${skill.source_ref}`"
            >
              {{ skill.source_ref }}
            </span>
          </div>
          <div class="col-enabled">
            <!-- 管理员：可点击切换 -->
            <button
              v-if="isAdmin"
              data-testid="toggle-enabled"
              class="toggle-pill"
              :class="skill.enabled ? 'is-on' : 'is-off'"
              :title="skill.enabled ? '点击禁用该版本' : '点击启用该版本'"
              @click="toggleEnabled(skill)"
            >
              <span class="toggle-dot" />
              <span class="toggle-text">{{ skill.enabled ? "已启用" : "已停用" }}</span>
            </button>
            <!-- 非管理员：只读 tag -->
            <span v-else class="ui-tag" :class="skill.enabled ? 'ui-tag-green' : 'ui-tag-grey'">
              {{ skill.enabled ? "已启用" : "已停用" }}
            </span>
          </div>
          <div class="col-date">
            <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">{{ formatDate(skill.created_at) }}</span>
          </div>
          <div class="col-ops">
            <button
              v-if="isAdmin"
              class="op-btn"
              data-testid="run-btn"
              title="试运行"
              @click="openRun(skill)"
            >
              <Play :size="14" class="text-[var(--color-ink-tertiary)]" />
            </button>
            <button
              v-if="isAdmin"
              class="op-btn"
              data-testid="audit-btn"
              title="执行审计"
              @click="openAudit(skill)"
            >
              <Activity :size="14" class="text-[var(--color-ink-tertiary)]" />
            </button>
            <button
              v-if="isAdmin"
              class="op-btn danger"
              data-testid="delete-btn"
              title="删除"
              @click="confirmDelete(skill)"
            >
              <Trash2 :size="14" class="text-[var(--color-danger)]" />
            </button>
            <span v-if="!isAdmin" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">-</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Register Modal -->
    <Teleport to="body">
      <div v-if="showCreate" class="modal-mask" data-testid="create-modal" @click.self="closeCreateModal">
        <div class="modal-panel modal-panel-wide">
          <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)] mb-3">注册 Skill</h3>
          <div class="form-grid">
            <label class="form-field">
              <span class="form-label">code <span class="text-[var(--color-danger)]">*</span></span>
              <input
                v-model="form.code"
                class="ui-input"
                data-testid="input-code"
                placeholder="如 enterprise_360_dd（小写字母开头，仅小写字母数字下划线）"
              />
            </label>
            <label class="form-field">
              <span class="form-label">version <span class="text-[var(--color-danger)]">*</span></span>
              <input
                v-model="form.version"
                class="ui-input"
                data-testid="input-version"
                placeholder="如 1.0.0（语义化版本 x.y.z）"
              />
            </label>
            <label class="form-field form-field-wide">
              <span class="form-label">名称 <span class="text-[var(--color-danger)]">*</span></span>
              <input
                v-model="form.name"
                class="ui-input"
                data-testid="input-name"
                placeholder="如 企业 360 背调"
              />
            </label>
            <label class="form-field form-field-wide">
              <span class="form-label">description（可选）</span>
              <textarea
                v-model="form.description"
                class="ui-input resize-none"
                data-testid="input-description"
                rows="2"
                placeholder="做什么 + 何时触发"
              />
            </label>
            <label class="form-field form-field-wide">
              <span class="form-label">sop_template（YAML）<span class="text-[var(--color-danger)]">*</span></span>
              <textarea
                v-model="form.sop_template"
                class="ui-input resize-none sop-textarea"
                data-testid="input-sop-template"
                rows="10"
                spellcheck="false"
                placeholder="name: enterprise-360-dd
description: 企业 360 背调
mcp_dependencies:
  - {server: qcc-company, required: true}
steps:
  - id: subject_verify
    title: 主体工商核验
    server: qcc-company
    tool: get_company_registration_info
    output: 主体身份档案
report_template: |
  ## 事实数据
  ...
  ## AI 分析
  ...
  ## 待人工确认项
  ..."
              />
              <span class="form-hint form-hint-warn">
                只填声明式 SOP 模板 YAML（name / description / mcp_dependencies / steps[server+tool] / report_template）；<b>绝不填 secret 或真实企业数据</b>。模板正文不含凭证，工具调用时 secret 仅从进程环境注入。
              </span>
            </label>
            <label class="form-field">
              <span class="form-label">source_ref（可选）</span>
              <input
                v-model="form.source_ref"
                class="ui-input"
                data-testid="input-source-ref"
                placeholder="如 企查查官方 skill URL / 导入文件名"
              />
            </label>
            <label class="form-field">
              <span class="form-label">allowed_roles（逗号分隔）</span>
              <input
                v-model="form.allowed_roles"
                class="ui-input"
                data-testid="input-roles"
                placeholder="如 admin,data_admin（留空 = 仅 super_admin）"
              />
            </label>
          </div>
          <div class="flex justify-end gap-2 mt-4">
            <button class="ui-btn ui-btn-ghost" data-testid="cancel-create" @click="closeCreateModal">取消</button>
            <button
              class="ui-btn ui-btn-primary"
              data-testid="submit-create"
              :disabled="creating || !form.code.trim() || !form.version.trim() || !form.name.trim() || !form.sop_template.trim()"
              @click="submitCreate"
            >
              {{ creating ? "注册中..." : "确认注册" }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete Confirmation -->
    <ConfirmDialog
      v-model:open="showDelete"
      title="删除 Skill"
      :message="`确定删除 Skill「${deleteTarget?.name}」v${deleteTarget?.version}？此为软删，已有执行审计行不硬删。`"
      danger
      @confirm="doDelete"
    />

    <!-- Audit Modal -->
    <Teleport to="body">
      <div v-if="showAudit" class="modal-mask" data-testid="audit-modal" @click.self="closeAudit">
        <div class="modal-panel modal-panel-wide">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">
              执行审计 · {{ auditTarget?.code }} v{{ auditTarget?.version }}
            </h3>
            <button class="ui-btn ui-btn-ghost" data-testid="audit-close" @click="closeAudit">关闭</button>
          </div>

          <LoadingSpinner v-if="auditLoading" text="加载审计..." />
          <EmptyState
            v-else-if="auditItems.length === 0"
            title="暂无执行记录"
            hint="该 skill 版本被执行时，审计行会在此分页展示（仅 digest，不含原始主体 / 事实 / 报告）"
          />
          <div v-else class="audit-table">
            <div class="audit-header">
              <div class="au-ver">version</div>
              <div class="au-ok">结果</div>
              <div class="au-dur">耗时(ms)</div>
              <div class="au-err">error_code</div>
              <div class="au-msg">error_message</div>
              <div class="au-date">时间</div>
            </div>
            <div v-for="ex in auditItems" :key="ex.id" class="audit-row">
              <div class="au-ver"><span class="row-code">{{ ex.skill_version }}</span></div>
              <div class="au-ok">
                <span class="ui-tag" :class="ex.ok ? 'ui-tag-green' : 'ui-tag-red'">
                  {{ ex.ok ? "成功" : "失败" }}
                </span>
              </div>
              <div class="au-dur text-[var(--text-small)] text-[var(--color-ink-secondary)]">{{ ex.duration_ms }}</div>
              <div class="au-err text-[var(--text-small)] text-[var(--color-ink-secondary)]">{{ ex.error_code ?? "-" }}</div>
              <div class="au-msg text-[var(--text-small)] text-[var(--color-ink-tertiary)]" :title="ex.error_message ?? ''">
                {{ ex.error_message ?? "-" }}
              </div>
              <div class="au-date text-[var(--text-small)] text-[var(--color-ink-tertiary)]">{{ formatDate(ex.created_at) }}</div>
            </div>
          </div>

          <div v-if="auditTotal > 0" class="flex items-center justify-between mt-4">
            <span data-testid="audit-page-info" class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
              {{ auditPageInfo }}
            </span>
            <div class="flex gap-2">
              <button
                class="ui-btn ui-btn-ghost"
                data-testid="audit-prev"
                :disabled="auditPage === 0 || auditLoading"
                @click="auditPrev"
              >
                上一页
              </button>
              <button
                class="ui-btn ui-btn-ghost"
                data-testid="audit-next"
                :disabled="!auditHasNext || auditLoading"
                @click="auditNext"
              >
                下一页
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Run (Trial) Modal -->
    <Teleport to="body">
      <div v-if="showRun" class="modal-mask" data-testid="run-modal" @click.self="closeRun">
        <div class="modal-panel modal-panel-wide">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">
              试运行 · {{ runTarget?.code }}
            </h3>
            <button class="ui-btn ui-btn-ghost" data-testid="run-close" @click="closeRun">关闭</button>
          </div>

          <div class="form-grid">
            <label class="form-field">
              <span class="form-label">version <span class="text-[var(--color-danger)]">*</span></span>
              <input
                v-model="runForm.version"
                class="ui-input"
                data-testid="run-input-version"
                placeholder="如 1.0.0"
              />
              <span class="form-hint">默认本行版本，可改为同 code 的其他版本</span>
            </label>
            <label class="form-field form-field-wide">
              <span class="form-label">subject（JSON）<span class="text-[var(--color-danger)]">*</span></span>
              <textarea
                v-model="runForm.subject"
                class="ui-input resize-none sop-textarea"
                data-testid="run-input-subject"
                rows="5"
                spellcheck="false"
                placeholder="{&quot;company_name&quot;: &quot;示例企业名称&quot;}"
              />
              <span class="form-hint form-hint-warn">
                subject 含企业敏感事实；产物 report 仅在本 modal 展示给管理角色，不缓存、不打印到控制台。
              </span>
            </label>
          </div>

          <div class="flex justify-end gap-2 mt-3">
            <button
              class="ui-btn ui-btn-primary"
              data-testid="run-submit"
              :disabled="running || !runForm.version.trim() || !runForm.subject.trim()"
              @click="submitRun"
            >
              {{ running ? "执行中..." : "执行试运行" }}
            </button>
          </div>

          <!-- 产物展示 -->
          <div v-if="runResult" class="run-result mt-4" data-testid="run-result">
            <div class="run-meta">
              <span class="ui-tag ui-tag-green">成功</span>
              <span class="text-[var(--text-small)] text-[var(--color-ink-secondary)]">
                耗时 {{ runResult.duration_ms }} ms · 审计 {{ shortAuditId }}
              </span>
            </div>
            <div class="run-steps" data-testid="run-steps">
              <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">步骤摘要（digest）：</span>
              <div v-for="s in runResult.steps" :key="s.id" class="run-step">
                <span class="row-code">{{ s.id }}</span>
                <span class="ui-tag" :class="s.ok ? 'ui-tag-green' : 'ui-tag-red'">{{ s.ok ? "ok" : "fail" }}</span>
                <span class="run-digest text-[var(--text-micro)] text-[var(--color-ink-tertiary)]" :title="s.digest ?? ''">{{ s.digest ?? "-" }}</span>
              </div>
            </div>
            <div class="run-report" data-testid="run-report">
              <div v-for="sec in reportSections" :key="sec.title" class="report-section">
                <div class="report-section-title">{{ sec.title }}</div>
                <pre class="report-section-body">{{ sec.body }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from "vue";
import { Plus, Trash2, Activity, Play, Filter } from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { useAuthStore } from "@/stores/auth";
import { useToast } from "@/composables/useToast";
import {
  listSkills,
  createSkill,
  enableSkill,
  disableSkill,
  deleteSkill,
  listExecutions,
  runSkill,
  type SkillDTO,
  type ExecutionDTO,
  type SkillRunResponse,
} from "@/services/skillRegistry";

// 与后端 SKILL_REGISTRY_ADMIN_ROLES 对齐（skill_registry_service.py）
const SKILL_ADMIN_ROLES = ["admin", "data_admin", "super_admin"];
// 与后端 _CODE_PATTERN / _VERSION_PATTERN 对齐（skill_registry_router.py）：
// 前端先挡一轮，避免无谓的 422 往返。
const CODE_PATTERN = /^[a-z][a-z0-9_]*$/;
const VERSION_PATTERN = /^\d+\.\d+\.\d+$/;

const authStore = useAuthStore();
const toast = useToast();
const isAdmin = computed(() => SKILL_ADMIN_ROLES.includes(authStore.userRole ?? ""));

const skills = ref<SkillDTO[]>([]);
const loading = ref(false);
const codeFilter = ref("");

const distinctCodes = computed(() => {
  const codes = Array.from(new Set(skills.value.map((s) => s.code)));
  codes.sort();
  return codes;
});
const filteredSkills = computed(() => {
  if (!codeFilter.value) return skills.value;
  return skills.value.filter((s) => s.code === codeFilter.value);
});

// --- register modal ---
const showCreate = ref(false);
const creating = ref(false);
const defaultForm = () => ({
  code: "",
  version: "",
  name: "",
  description: "",
  sop_template: "",
  source_ref: "",
  allowed_roles: "",
});
const form = reactive(defaultForm());

function openCreateModal() {
  Object.assign(form, defaultForm());
  showCreate.value = true;
}

function closeCreateModal() {
  showCreate.value = false;
}

// --- error helper（不引入 any） ---
interface AxiosLikeError {
  response?: { status?: number; data?: { detail?: string } };
}
function errorStatus(e: unknown): number | undefined {
  return (e as AxiosLikeError).response?.status;
}
function errorDetail(e: unknown, fallback: string): string {
  const detail = (e as AxiosLikeError).response?.data?.detail;
  return detail ?? fallback;
}

async function submitCreate() {
  if (!form.code.trim() || !form.version.trim() || !form.name.trim() || !form.sop_template.trim()) {
    toast.error("请填写必填项");
    return;
  }
  // 前端格式校验（与后端 pattern 对齐，提前挡掉非法输入）
  if (!CODE_PATTERN.test(form.code.trim())) {
    toast.error("code 必须小写字母开头，仅含小写字母 / 数字 / 下划线");
    return;
  }
  if (!VERSION_PATTERN.test(form.version.trim())) {
    toast.error("version 必须为语义化版本 x.y.z（如 1.0.0）");
    return;
  }
  const roles = form.allowed_roles
    .split(",")
    .map((r) => r.trim())
    .filter(Boolean);
  creating.value = true;
  try {
    await createSkill({
      code: form.code.trim(),
      version: form.version.trim(),
      name: form.name.trim(),
      sop_template: form.sop_template,
      ...(form.description.trim() ? { description: form.description.trim() } : {}),
      ...(form.source_ref.trim() ? { source_ref: form.source_ref.trim() } : {}),
      ...(roles.length ? { allowed_roles: roles } : {}),
    });
    toast.success("已注册");
    showCreate.value = false;
    // Reset the version filter so a newly registered skill of a different
    // code is visible (otherwise it would be hidden by the active filter).
    codeFilter.value = "";
    await loadSkills();
  } catch (e) {
    const status = errorStatus(e);
    if (status === 409) toast.error(errorDetail(e, "该 (code, version) 已存在"));
    else if (status === 422) toast.error(errorDetail(e, "参数校验失败（code/version 格式或 SOP 模板非法）"));
    else if (status === 403) toast.error("无权注册 Skill");
    else toast.error("注册失败");
  } finally {
    creating.value = false;
  }
}

// --- enable / disable ---
async function toggleEnabled(skill: SkillDTO) {
  try {
    if (skill.enabled) {
      await disableSkill(skill.id);
      toast.success("已禁用");
    } else {
      await enableSkill(skill.id);
      toast.success("已启用");
    }
    await loadSkills();
  } catch (e) {
    const status = errorStatus(e);
    if (status === 403) toast.error("无权操作");
    else toast.error(errorDetail(e, "操作失败"));
  }
}

// --- delete ---
const showDelete = ref(false);
const deleteTarget = ref<SkillDTO | null>(null);

function confirmDelete(skill: SkillDTO) {
  deleteTarget.value = skill;
  showDelete.value = true;
}

async function doDelete() {
  if (!deleteTarget.value) return;
  const target = deleteTarget.value;
  try {
    await deleteSkill(target.id);
    toast.success("已删除");
    skills.value = skills.value.filter((s) => s.id !== target.id);
    deleteTarget.value = null;
    showDelete.value = false;
  } catch (e) {
    const status = errorStatus(e);
    if (status === 403) toast.error("无权删除");
    else toast.error(errorDetail(e, "删除失败"));
  }
}

// --- audit modal ---
const showAudit = ref(false);
const auditTarget = ref<SkillDTO | null>(null);
const auditItems = ref<ExecutionDTO[]>([]);
const auditTotal = ref(0);
const auditPage = ref(0);
const auditLimit = 10;
const auditLoading = ref(false);

const auditHasNext = computed(
  () => (auditPage.value + 1) * auditLimit < auditTotal.value,
);

const auditPageInfo = computed(() => {
  const start = auditTotal.value === 0 ? 0 : auditPage.value * auditLimit + 1;
  const end = Math.min((auditPage.value + 1) * auditLimit, auditTotal.value);
  return `${start}-${end} / 共 ${auditTotal.value}`;
});

async function openAudit(skill: SkillDTO) {
  auditTarget.value = skill;
  auditPage.value = 0;
  showAudit.value = true;
  await loadAudit();
}

function closeAudit() {
  showAudit.value = false;
}

async function loadAudit() {
  if (!auditTarget.value) return;
  auditLoading.value = true;
  try {
    const res = await listExecutions(auditTarget.value.id, {
      limit: auditLimit,
      offset: auditPage.value * auditLimit,
    });
    auditItems.value = res.items;
    auditTotal.value = res.total;
  } catch (e) {
    const status = errorStatus(e);
    if (status === 403) toast.error("无权查询执行审计");
    else toast.error(errorDetail(e, "加载审计失败"));
    auditItems.value = [];
    auditTotal.value = 0;
  } finally {
    auditLoading.value = false;
  }
}

function auditPrev() {
  if (auditPage.value > 0) {
    auditPage.value -= 1;
    loadAudit();
  }
}

function auditNext() {
  if (auditHasNext.value) {
    auditPage.value += 1;
    loadAudit();
  }
}

// --- run (trial) modal ---
const showRun = ref(false);
const runTarget = ref<SkillDTO | null>(null);
const running = ref(false);
const runResult = ref<SkillRunResponse | null>(null);
const defaultRunForm = () => ({ version: "", subject: "" });
const runForm = reactive(defaultRunForm());

function openRun(skill: SkillDTO) {
  runTarget.value = skill;
  runResult.value = null;
  Object.assign(runForm, defaultRunForm());
  // 默认本行版本（可改为同 code 其他版本）
  runForm.version = skill.version;
  showRun.value = true;
}

function closeRun() {
  showRun.value = false;
  // 关闭即丢弃产物 - 不缓存企业敏感事实
  runResult.value = null;
}

const shortAuditId = computed(() => {
  const id = runResult.value?.execution_audit_id ?? "";
  return id ? id.slice(0, 8) : "-";
});

/**
 * 把 report 文本按 `## ` 标题切成分区（事实数据 / AI 分析 / 待人工确认项）。
 * 模板 report_template 用 markdown 二级标题分区；若 LLM 产物没带标题，
 * 回退为整段文本一个分区。只做展示切分，不改写原文。
 */
const reportSections = computed(() => {
  const text = runResult.value?.report ?? "";
  if (!text) return [];
  const lines = text.split("\n");
  const sections: { title: string; body: string }[] = [];
  let current: { title: string; body: string } | null = null;
  for (const line of lines) {
    if (line.startsWith("## ")) {
      if (current) sections.push(current);
      current = { title: line.slice(3).trim() || "（无标题）", body: "" };
    } else if (current) {
      current.body += (current.body ? "\n" : "") + line;
    } else {
      // 标题前的引导文本归到首个分区
      current = { title: "报告产物", body: line };
    }
  }
  if (current) sections.push(current);
  return sections.length > 0 ? sections : [{ title: "报告产物", body: text }];
});

async function submitRun() {
  if (!runTarget.value) return;
  if (!VERSION_PATTERN.test(runForm.version.trim())) {
    toast.error("version 必须为语义化版本 x.y.z（如 1.0.0）");
    return;
  }
  let subject: Record<string, unknown>;
  try {
    const parsed = JSON.parse(runForm.subject);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("not object");
    }
    subject = parsed as Record<string, unknown>;
  } catch {
    toast.error("subject 必须是合法 JSON 对象");
    return;
  }
  // Mirror backend `subject: dict = Field(min_length=1)` so an empty `{}`
  // is rejected here with a clear message instead of a misleading 422.
  if (Object.keys(subject).length === 0) {
    toast.error("subject 不能为空对象");
    return;
  }
  running.value = true;
  runResult.value = null;
  try {
    const res = await runSkill(runTarget.value.id, {
      version: runForm.version.trim(),
      subject,
    });
    // 产物只在内存中持有供本 modal 展示；关闭即丢弃，不缓存。
    runResult.value = res;
    toast.success("试运行完成");
  } catch (e) {
    const status = errorStatus(e);
    if (status === 403) toast.error(errorDetail(e, "无权执行或角色不在 allowed_roles"));
    else if (status === 404) toast.error(errorDetail(e, "skill 或该版本未注册"));
    else if (status === 409) toast.error(errorDetail(e, "skill 已停用"));
    else if (status === 422) toast.error(errorDetail(e, "SOP 模板解析失败"));
    else toast.error(errorDetail(e, "试运行失败（工具或 LLM 错误）"));
  } finally {
    running.value = false;
  }
}

// --- helpers ---
function formatDate(iso: string) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function loadSkills() {
  loading.value = true;
  try {
    skills.value = await listSkills();
  } catch (e) {
    toast.error(errorDetail(e, "加载 Skill 失败"));
    skills.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadSkills();
});
</script>

<style scoped>
.skill-container {
  background: #ffffff;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 3px rgba(0, 0, 0, 0.06);
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.filter-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-ink-tertiary);
  font-weight: 500;
}
.filter-select {
  width: 220px;
}

.list-header {
  display: grid;
  grid-template-columns: 1.2fr 90px 1.6fr 110px 140px 130px;
  gap: 0;
  padding: 10px 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e5e7eb;
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  align-items: center;
}

.list-row {
  display: grid;
  grid-template-columns: 1.2fr 90px 1.6fr 110px 140px 130px;
  gap: 0;
  padding: 12px 16px;
  border-bottom: 1px solid #f3f4f6;
  align-items: center;
  transition: background 0.1s;
}

.list-row:last-child {
  border-bottom: none;
}

.list-row:hover {
  background: #f9fafb;
}

.row-code {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
  font-family: monospace;
  word-break: break-all;
}

.row-version {
  font-size: 12px;
  font-family: monospace;
  color: var(--color-ink-secondary);
}

.col-name {
  display: flex;
  align-items: center;
  min-width: 0;
}

.row-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.col-enabled {
  display: flex;
  align-items: center;
}

.col-ops {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* toggle pill */
.toggle-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px 4px 6px;
  border-radius: 999px;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.15s;
}
.toggle-pill.is-on {
  background: rgba(34, 197, 94, 0.12);
  color: #15803d;
  border-color: rgba(34, 197, 94, 0.3);
}
.toggle-pill.is-off {
  background: #f3f4f6;
  color: #6b7280;
  border-color: #e5e7eb;
}
.toggle-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}
.toggle-pill:hover {
  filter: brightness(0.96);
}

.ui-tag-green {
  display: inline-flex;
  align-items: center;
  background: rgba(34, 197, 94, 0.12);
  color: #15803d;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
.ui-tag-grey {
  display: inline-flex;
  align-items: center;
  background: #e5e7eb;
  color: #6b7280;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
.ui-tag-red {
  display: inline-flex;
  align-items: center;
  background: rgba(239, 68, 68, 0.1);
  color: #b91c1c;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
.ui-tag-blue {
  display: inline-flex;
  align-items: center;
  background: #eef2ff;
  color: #4338ca;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  font-family: monospace;
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.op-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  transition: background 0.1s;
}
.op-btn:hover {
  background: var(--interactive-hover-bg);
}
.op-btn.danger:hover {
  background: rgba(239, 68, 68, 0.08);
}

/* modals */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-panel {
  background: white;
  border-radius: 12px;
  padding: 20px 24px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
}
.modal-panel-wide {
  max-width: 680px;
  max-height: 85vh;
  overflow-y: auto;
}

/* form */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
}
.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.form-field-wide {
  grid-column: 1 / -1;
}
.form-label {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  font-weight: 500;
}
.form-hint {
  font-size: 11px;
  color: var(--color-ink-tertiary);
  line-height: 1.5;
}
.form-hint-warn {
  color: #b45309;
}
.sop-textarea {
  font-family: monospace;
  font-size: 12px;
  line-height: 1.5;
}

/* audit table */
.audit-table {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
.audit-header,
.audit-row {
  display: grid;
  grid-template-columns: 80px 70px 90px 1fr 1.4fr 130px;
  gap: 0;
  padding: 8px 12px;
  align-items: center;
}
.audit-header {
  background: #f8f9fa;
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  border-bottom: 1px solid #e5e7eb;
}
.audit-row {
  border-bottom: 1px solid #f3f4f6;
  font-size: 12px;
}
.audit-row:last-child {
  border-bottom: none;
}
.au-msg {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* run result */
.run-result {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  background: #fafbfc;
}
.run-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.run-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px dashed #e5e7eb;
}
.run-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.run-digest {
  font-family: monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}
.run-report {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.report-section {
  border-left: 3px solid #6366f1;
  padding-left: 10px;
}
.report-section-title {
  font-size: 12px;
  font-weight: 600;
  color: #4338ca;
  margin-bottom: 4px;
}
.report-section-body {
  font-size: 12px;
  color: var(--color-ink);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: var(--font-body);
  line-height: 1.6;
}
</style>
