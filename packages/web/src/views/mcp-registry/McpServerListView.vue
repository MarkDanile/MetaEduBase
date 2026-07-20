<template>
  <div class="p-6">
    <PageHeader title="MCP 服务" subtitle="注册与管理 MCP server（凭证只填环境变量引用名，绝不填真实 token）">
      <template #extra>
        <button
          v-if="isAdmin"
          class="ui-btn ui-btn-primary"
          data-testid="register-btn"
          @click="openCreateModal"
        >
          <Plus :size="16" /> 注册服务
        </button>
      </template>
    </PageHeader>

    <div class="mt-4">
      <LoadingSpinner v-if="loading" text="加载 MCP 服务..." />
      <EmptyState
        v-else-if="servers.length === 0"
        title="暂无 MCP 服务"
        hint="点击右上角「注册服务」接入第一个 MCP server"
      />
      <div v-else class="server-container">
        <!-- Header -->
        <div class="list-header">
          <div class="col-code">code</div>
          <div class="col-name">名称</div>
          <div class="col-transport">transport</div>
          <div class="col-url">server_url</div>
          <div class="col-enabled">状态</div>
          <div class="col-date">创建时间</div>
          <div class="col-ops">操作</div>
        </div>

        <!-- Rows -->
        <div
          v-for="server in servers"
          :key="server.id"
          class="list-row"
          data-testid="server-row"
        >
          <div class="col-code">
            <span class="row-code">{{ server.code }}</span>
          </div>
          <div class="col-name">
            <span class="row-name">{{ server.name }}</span>
            <span v-if="server.credential_ref" class="ui-tag-blue text-[var(--text-micro)] ml-2" title="凭证引用名">
              {{ server.credential_ref }}
            </span>
          </div>
          <div class="col-transport">
            <span class="text-[var(--text-small)] text-[var(--color-ink-secondary)]">{{ server.transport }}</span>
          </div>
          <div class="col-url">
            <span class="row-url" :title="server.server_url">{{ server.server_url }}</span>
          </div>
          <div class="col-enabled">
            <!-- 管理员：可点击切换 -->
            <button
              v-if="isAdmin"
              data-testid="toggle-enabled"
              class="toggle-pill"
              :class="server.enabled ? 'is-on' : 'is-off'"
              :title="server.enabled ? '点击禁用' : '点击启用（将触发连通校验）'"
              @click="toggleEnabled(server)"
            >
              <span class="toggle-dot" />
              <span class="toggle-text">{{ server.enabled ? "已启用" : "已停用" }}</span>
            </button>
            <!-- 非管理员：只读 tag -->
            <span v-else class="ui-tag" :class="server.enabled ? 'ui-tag-green' : 'ui-tag-grey'">
              {{ server.enabled ? "已启用" : "已停用" }}
            </span>
          </div>
          <div class="col-date">
            <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">{{ formatDate(server.created_at) }}</span>
          </div>
          <div class="col-ops">
            <button
              v-if="isAdmin"
              class="op-btn"
              data-testid="audit-btn"
              title="调用审计"
              @click="openAudit(server)"
            >
              <Activity :size="14" class="text-[var(--color-ink-tertiary)]" />
            </button>
            <button
              v-if="isAdmin"
              class="op-btn danger"
              data-testid="delete-btn"
              title="删除"
              @click="confirmDelete(server)"
            >
              <Trash2 :size="14" class="text-[var(--color-danger)]" />
            </button>
            <span v-if="!isAdmin" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">—</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Register Modal -->
    <Teleport to="body">
      <div v-if="showCreate" class="modal-mask" data-testid="create-modal" @click.self="closeCreateModal">
        <div class="modal-panel modal-panel-wide">
          <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)] mb-3">注册 MCP 服务</h3>
          <div class="form-grid">
            <label class="form-field">
              <span class="form-label">code <span class="text-[var(--color-danger)]">*</span></span>
              <input
                v-model="form.code"
                class="ui-input"
                data-testid="input-code"
                placeholder="如 qcc（小写字母开头，仅小写字母数字下划线）"
              />
            </label>
            <label class="form-field">
              <span class="form-label">名称 <span class="text-[var(--color-danger)]">*</span></span>
              <input
                v-model="form.name"
                class="ui-input"
                data-testid="input-name"
                placeholder="如 企查查"
              />
            </label>
            <label class="form-field form-field-wide">
              <span class="form-label">server_url <span class="text-[var(--color-danger)]">*</span></span>
              <input
                v-model="form.server_url"
                class="ui-input"
                data-testid="input-url"
                placeholder="https://mcp.example.com/mcp"
              />
            </label>
            <label class="form-field">
              <span class="form-label">transport</span>
              <select v-model="form.transport" class="ui-input" data-testid="input-transport">
                <option value="streamable_http">streamable_http</option>
                <option value="sse">sse</option>
              </select>
            </label>
            <label class="form-field">
              <span class="form-label">timeout_ms</span>
              <input
                v-model.number="form.timeout_ms"
                type="number"
                class="ui-input"
                data-testid="input-timeout"
                min="1000"
                step="1000"
              />
            </label>
            <label class="form-field form-field-wide">
              <span class="form-label">credential_ref（env 引用名）</span>
              <input
                v-model="form.credential_ref"
                class="ui-input"
                data-testid="input-credential-ref"
                placeholder="如 QCC_MCP_TOKEN"
              />
              <span class="form-hint form-hint-warn">
                只填环境变量引用名（大写字母开头，仅大写字母 / 数字 / 下划线）；<b>绝不填真实 token</b>。secret 仅存在于进程环境。
              </span>
            </label>
            <label class="form-field form-field-wide">
              <span class="form-label">allowed_roles（逗号分隔）</span>
              <input
                v-model="form.allowed_roles"
                class="ui-input"
                data-testid="input-roles"
                placeholder="如 admin,data_admin（留空 = 仅 super_admin）"
              />
            </label>
            <label class="form-field form-field-wide">
              <span class="form-label">description（可选）</span>
              <textarea
                v-model="form.description"
                class="ui-input resize-none"
                data-testid="input-description"
                rows="2"
                placeholder="服务用途说明"
              />
            </label>
          </div>
          <div class="flex justify-end gap-2 mt-4">
            <button class="ui-btn ui-btn-ghost" data-testid="cancel-create" @click="closeCreateModal">取消</button>
            <button
              class="ui-btn ui-btn-primary"
              data-testid="submit-create"
              :disabled="creating || !form.code.trim() || !form.name.trim() || !form.server_url.trim()"
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
      title="删除 MCP 服务"
      :message="`确定删除 MCP 服务「${deleteTarget?.name}」？此为软删，已有调用审计行不硬删。`"
      danger
      @confirm="doDelete"
    />

    <!-- Audit Modal -->
    <Teleport to="body">
      <div v-if="showAudit" class="modal-mask" data-testid="audit-modal" @click.self="closeAudit">
        <div class="modal-panel modal-panel-wide">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">
              调用审计 · {{ auditTarget?.code }}
            </h3>
            <button class="ui-btn ui-btn-ghost" data-testid="audit-close" @click="closeAudit">关闭</button>
          </div>

          <LoadingSpinner v-if="auditLoading" text="加载审计..." />
          <EmptyState
            v-else-if="auditItems.length === 0"
            title="暂无调用记录"
            hint="该 server 启用后被调用时，审计行会在此分页展示"
          />
          <div v-else class="audit-table">
            <div class="audit-header">
              <div class="au-tool">tool</div>
              <div class="au-ok">结果</div>
              <div class="au-dur">耗时(ms)</div>
              <div class="au-err">error_code</div>
              <div class="au-msg">error_message</div>
              <div class="au-date">时间</div>
            </div>
            <div v-for="inv in auditItems" :key="inv.id" class="audit-row">
              <div class="au-tool"><span class="row-code">{{ inv.tool_name }}</span></div>
              <div class="au-ok">
                <span class="ui-tag" :class="inv.ok ? 'ui-tag-green' : 'ui-tag-red'">
                  {{ inv.ok ? "成功" : "失败" }}
                </span>
              </div>
              <div class="au-dur text-[var(--text-small)] text-[var(--color-ink-secondary)]">{{ inv.duration_ms }}</div>
              <div class="au-err text-[var(--text-small)] text-[var(--color-ink-secondary)]">{{ inv.error_code ?? "—" }}</div>
              <div class="au-msg text-[var(--text-small)] text-[var(--color-ink-tertiary)]" :title="inv.error_message ?? ''">
                {{ inv.error_message ?? "—" }}
              </div>
              <div class="au-date text-[var(--text-small)] text-[var(--color-ink-tertiary)]">{{ formatDate(inv.created_at) }}</div>
            </div>
          </div>

          <div class="flex items-center justify-between mt-4">
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from "vue";
import { Plus, Trash2, Activity } from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { useAuthStore } from "@/stores/auth";
import { useToast } from "@/composables/useToast";
import {
  listMcpServers,
  createMcpServer,
  enableMcpServer,
  disableMcpServer,
  deleteMcpServer,
  listInvocations,
  type McpServerDTO,
  type InvocationDTO,
  type McpTransport,
} from "@/services/mcpRegistry";

// 与后端 MCP_REGISTRY_ADMIN_ROLES 对齐
const MCP_ADMIN_ROLES = ["admin", "data_admin", "super_admin"];

const authStore = useAuthStore();
const toast = useToast();
const isAdmin = computed(() => MCP_ADMIN_ROLES.includes(authStore.userRole ?? ""));

const servers = ref<McpServerDTO[]>([]);
const loading = ref(false);

// --- register modal ---
const showCreate = ref(false);
const creating = ref(false);
const defaultForm = () => ({
  code: "",
  name: "",
  server_url: "",
  transport: "streamable_http" as McpTransport,
  credential_ref: "",
  allowed_roles: "",
  timeout_ms: 30000,
  description: "",
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
  if (!form.code.trim() || !form.name.trim() || !form.server_url.trim()) {
    toast.error("请填写必填项");
    return;
  }
  const roles = form.allowed_roles
    .split(",")
    .map((r) => r.trim())
    .filter(Boolean);
  creating.value = true;
  try {
    await createMcpServer({
      code: form.code.trim(),
      name: form.name.trim(),
      server_url: form.server_url.trim(),
      transport: form.transport,
      timeout_ms: Number(form.timeout_ms) || 30000,
      ...(form.credential_ref.trim() ? { credential_ref: form.credential_ref.trim() } : {}),
      ...(roles.length ? { allowed_roles: roles } : {}),
      ...(form.description.trim() ? { description: form.description.trim() } : {}),
    });
    toast.success("已注册");
    showCreate.value = false;
    await loadServers();
  } catch (e) {
    const status = errorStatus(e);
    if (status === 409) toast.error(errorDetail(e, "code 已存在"));
    else if (status === 422) toast.error(errorDetail(e, "参数校验失败（credential_ref 格式或 transport 非法）"));
    else if (status === 403) toast.error("无权注册 MCP 服务");
    else toast.error("注册失败");
  } finally {
    creating.value = false;
  }
}

// --- enable / disable ---
async function toggleEnabled(server: McpServerDTO) {
  try {
    if (server.enabled) {
      await disableMcpServer(server.id);
      toast.success("已禁用");
    } else {
      // probe=true 触发真实连通校验；失败不阻塞启用，warning 回显给用户
      const res = await enableMcpServer(server.id, true);
      toast.success("已启用");
      if (res.warning) toast.warning(res.warning);
    }
    await loadServers();
  } catch (e) {
    const status = errorStatus(e);
    if (status === 403) toast.error("无权操作");
    else toast.error(errorDetail(e, "操作失败"));
  }
}

// --- delete ---
const showDelete = ref(false);
const deleteTarget = ref<McpServerDTO | null>(null);

function confirmDelete(server: McpServerDTO) {
  deleteTarget.value = server;
  showDelete.value = true;
}

async function doDelete() {
  if (!deleteTarget.value) return;
  const target = deleteTarget.value;
  try {
    await deleteMcpServer(target.id);
    toast.success("已删除");
    servers.value = servers.value.filter((s) => s.id !== target.id);
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
const auditTarget = ref<McpServerDTO | null>(null);
const auditItems = ref<InvocationDTO[]>([]);
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

async function openAudit(server: McpServerDTO) {
  auditTarget.value = server;
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
    const res = await listInvocations(auditTarget.value.id, {
      limit: auditLimit,
      offset: auditPage.value * auditLimit,
    });
    auditItems.value = res.items;
    auditTotal.value = res.total;
  } catch (e) {
    const status = errorStatus(e);
    if (status === 403) toast.error("无权查询调用审计");
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

// --- helpers ---
function formatDate(iso: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function loadServers() {
  loading.value = true;
  try {
    servers.value = await listMcpServers();
  } catch (e) {
    toast.error(errorDetail(e, "加载 MCP 服务失败"));
    servers.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadServers();
});
</script>

<style scoped>
.server-container {
  background: #ffffff;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 3px rgba(0, 0, 0, 0.06);
}

.list-header {
  display: grid;
  grid-template-columns: 120px 1.2fr 140px 1.6fr 110px 140px 110px;
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
  grid-template-columns: 120px 1.2fr 140px 1.6fr 110px 140px 110px;
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

.col-url {
  min-width: 0;
}

.row-url {
  font-size: 12px;
  color: var(--color-ink-secondary);
  font-family: monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block;
  max-width: 100%;
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
  max-width: 640px;
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

/* audit table */
.audit-table {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
.audit-header,
.audit-row {
  display: grid;
  grid-template-columns: 1.2fr 70px 90px 1fr 1.4fr 130px;
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
</style>
