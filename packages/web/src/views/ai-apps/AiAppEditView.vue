<template>
  <div class="p-6 max-w-3xl mx-auto">
    <button class="back-btn" @click="router.push('/ai-apps/admin')">
      <ArrowLeft :size="14" /> 返回管理
    </button>

    <PageHeader :title="isEdit ? '编辑应用' : '新建应用'" :subtitle="isEdit ? `编辑 ${form.name || ''}` : '注册新的 AI 应用到应用广场'">
      <template #extra v-if="isEdit && app">
        <button class="ui-btn ui-btn-ghost" @click="copyShareLink">
          复制分享链接
        </button>
        <button class="ui-btn ui-btn-ghost" @click="copyApiToken">
          复制 API Token
        </button>
      </template>
    </PageHeader>

    <div v-if="loading" class="loading-state">
      <LoadingSpinner text="加载应用..." />
    </div>

    <form v-else class="edit-form" @submit.prevent="doSave">
      <!-- 基础信息 -->
      <section class="form-section">
        <h3 class="section-title">基础信息</h3>

        <div class="form-row">
          <label class="form-label">
            应用编号 <span class="text-[var(--color-danger)]">*</span>
            <span class="label-hint">稳定唯一标识，如 APP-001</span>
          </label>
          <input
            v-model="form.code"
            class="ui-input"
            :disabled="isEdit"
            placeholder="APP-001"
            required
            maxlength="50"
          />
        </div>

        <div class="form-row">
          <label class="form-label">
            应用名称 <span class="text-[var(--color-danger)]">*</span>
          </label>
          <input v-model="form.name" class="ui-input" placeholder="课程能力图谱智能体工具" required maxlength="200" />
        </div>

        <div class="form-row">
          <label class="form-label">描述</label>
          <textarea v-model="form.description" class="ui-input" rows="3" placeholder="描述应用的功能和使用场景" maxlength="2000" />
        </div>

        <div class="form-row-2col">
          <div class="form-row">
            <label class="form-label">分类</label>
            <input v-model="form.category" class="ui-input" placeholder="learning" maxlength="100" />
          </div>
          <div class="form-row">
            <label class="form-label">图标</label>
            <input v-model="form.icon" class="ui-input" placeholder="🤖 或图片 URL" maxlength="500" />
          </div>
        </div>

        <div class="form-row-2col">
          <div class="form-row">
            <label class="form-label">版本</label>
            <input v-model="form.version" class="ui-input" placeholder="1.0.0" maxlength="20" />
          </div>
          <div class="form-row">
            <label class="form-label">负责人</label>
            <input v-model="form.owner" class="ui-input" placeholder="system" maxlength="200" />
          </div>
        </div>
      </section>

      <!-- 访问配置 -->
      <section class="form-section">
        <h3 class="section-title">访问配置</h3>

        <div class="form-row-2col">
          <div class="form-row">
            <label class="form-label">可见性</label>
            <select v-model="form.visibility" class="ui-input">
              <option value="internal">内部（仅登录用户）</option>
              <option value="role_limited">角色限定</option>
              <option value="public">公开</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">入口类型</label>
            <select v-model="form.entry_type" class="ui-input">
              <option value="internal_route">内部路由</option>
              <option value="external_url">外部链接</option>
              <option value="embedded">嵌入模式</option>
              <option value="api">API 暴露</option>
            </select>
          </div>
        </div>

        <div v-if="form.entry_type === 'internal_route'" class="form-row">
          <label class="form-label">内部路由</label>
          <input v-model="form.route_path" class="ui-input" placeholder="/apps/course-capability-map" maxlength="200" />
        </div>

        <div v-if="form.entry_type === 'external_url'" class="form-row">
          <label class="form-label">外部链接</label>
          <input v-model="form.external_url" class="ui-input" placeholder="https://..." maxlength="500" />
        </div>
      </section>

      <!-- 配置与能力 -->
      <section class="form-section">
        <h3 class="section-title">配置与能力</h3>

        <div class="form-row">
          <label class="form-label">所需底座能力</label>
          <div class="capability-input">
            <input
              v-model="newCapability"
              class="ui-input"
              placeholder="输入能力名称后回车添加"
              @keydown.enter.prevent="addCapability"
            />
            <button type="button" class="ui-btn ui-btn-ghost" @click="addCapability">添加</button>
          </div>
          <div v-if="form.required_capabilities?.length" class="capability-tags">
            <span
              v-for="cap in form.required_capabilities"
              :key="cap"
              class="cap-tag"
            >
              {{ cap }}
              <button type="button" class="cap-remove" @click="removeCapability(cap)">×</button>
            </span>
          </div>
        </div>

        <div class="form-row">
          <label class="form-label">
            配置 JSON
            <span class="label-hint">应用特定的配置项</span>
          </label>
          <textarea
            v-model="configSchemaText"
            class="ui-input font-mono"
            rows="6"
            placeholder="{'key': 'value'}"
          />
          <p v-if="configError" class="field-error">{{ configError }}</p>
        </div>
      </section>

      <!-- Token 信息（编辑时显示） -->
      <section v-if="isEdit && app" class="form-section">
        <h3 class="section-title">访问凭证</h3>

        <div class="form-row">
          <label class="form-label">分享 Token</label>
          <div class="token-row">
            <input :value="app.share_token || '（未生成）'" class="ui-input font-mono" readonly />
            <button type="button" class="ui-btn ui-btn-ghost" @click="regenerateShareToken">
              重新生成
            </button>
          </div>
        </div>

        <div class="form-row">
          <label class="form-label">API Token</label>
          <div class="token-row">
            <input :value="app.api_token ? `${app.api_token.slice(0, 8)}...` : '（未生成）'" class="ui-input font-mono" readonly />
            <button type="button" class="ui-btn ui-btn-ghost" @click="regenerateApiToken">
              重新生成
            </button>
          </div>
        </div>
      </section>

      <!-- 提交 -->
      <div class="form-actions">
        <button type="button" class="ui-btn ui-btn-ghost" @click="router.push('/ai-apps/admin')">
          取消
        </button>
        <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft } from 'lucide-vue-next';
import PageHeader from '@/components/PageHeader.vue';
import LoadingSpinner from '@/components/LoadingSpinner.vue';
import { aiAppsApi, type AiAppAdmin } from '@/services/aiAppsApi';

type AiAppUpdateInput = Partial<Pick<AiAppAdmin,
  'name' | 'description' | 'category' | 'icon' | 'version' | 'owner' |
  'visibility' | 'entry_type' | 'route_path' | 'external_url' |
  'required_capabilities' | 'config_schema'
>>;
// create 时必填 name（其他 backend default 已覆盖），code 必填
type AiAppCreateInput = AiAppUpdateInput & { code: string; name: string };
import { useToast } from '@/composables/useToast';

const route = useRoute();
const router = useRouter();
const toast = useToast();

const appId = computed(() => route.params.id as string | undefined);
const isEdit = computed(() => !!appId.value && appId.value !== 'create');

const loading = ref(false);
const saving = ref(false);
const app = ref<AiAppAdmin | null>(null);
const newCapability = ref('');
const configError = ref('');

const form = reactive({
  code: '',
  name: '',
  description: '',
  category: '',
  icon: '',
  version: '1.0.0',
  owner: '',
  visibility: 'internal',
  entry_type: 'internal_route',
  route_path: '',
  external_url: '',
  required_capabilities: [] as string[],
});

const configSchemaText = ref('{}');

function parseConfig() {
  if (!configSchemaText.value.trim()) return null;
  try {
    const parsed = JSON.parse(configSchemaText.value);
    configError.value = '';
    return parsed;
  } catch {
    configError.value = 'JSON 格式错误';
    return undefined;
  }
}

function addCapability() {
  const cap = newCapability.value.trim();
  if (!cap) return;
  if (!form.required_capabilities!.includes(cap)) {
    form.required_capabilities!.push(cap);
  }
  newCapability.value = '';
}

function removeCapability(cap: string) {
  form.required_capabilities = form.required_capabilities!.filter(c => c !== cap);
}

async function loadApp() {
  if (!isEdit.value) return;
  loading.value = true;
  try {
    // BUG-018 AC-4: 编辑页需显示 share_token/api_token，超管 ?scope=admin 拿 Admin。
    const a = (await aiAppsApi.get(appId.value!, { admin_scope: true })) as AiAppAdmin;
    app.value = a;
    form.code = a.code;
    form.name = a.name;
    form.description = a.description || '';
    form.category = a.category || '';
    form.icon = a.icon || '';
    form.version = a.version;
    form.owner = a.owner || '';
    form.visibility = a.visibility;
    form.entry_type = a.entry_type;
    form.route_path = a.route_path || '';
    form.external_url = a.external_url || '';
    form.required_capabilities = [...(a.required_capabilities || [])];
    configSchemaText.value = a.config_schema ? JSON.stringify(a.config_schema, null, 2) : '{}';
  } catch {
    toast.error('加载应用失败');
  } finally {
    loading.value = false;
  }
}

async function doSave() {
  if (!form.name.trim() || !form.code.trim()) {
    toast.error('请填写必填项');
    return;
  }
  const config = parseConfig();
  if (config === undefined) {
    toast.error('配置 JSON 格式错误');
    return;
  }

  saving.value = true;
  try {
    const data: AiAppUpdateInput = {
      name: form.name,
      description: form.description || null,
      category: form.category || null,
      icon: form.icon || null,
      version: form.version,
      owner: form.owner || null,
      visibility: form.visibility,
      entry_type: form.entry_type,
      route_path: form.route_path || null,
      external_url: form.external_url || null,
      required_capabilities: form.required_capabilities!.length ? form.required_capabilities : null,
      config_schema: config,
    };

    if (isEdit.value) {
      await aiAppsApi.update(appId.value!, data);
      toast.success('应用已更新');
    } else {
      const createData: AiAppCreateInput = {
        code: form.code,
        name: form.name,
        description: form.description || null,
        category: form.category || null,
        icon: form.icon || null,
        version: form.version,
        owner: form.owner || null,
        visibility: form.visibility,
        entry_type: form.entry_type,
        route_path: form.route_path || null,
        external_url: form.external_url || null,
        required_capabilities: form.required_capabilities!.length ? form.required_capabilities : null,
        config_schema: config,
      };
      await aiAppsApi.create(createData);
      toast.success('应用已创建');
    }
    router.push('/ai-apps/admin');
  } catch (err: unknown) {
    toast.error((err as Error).message || '保存失败');
  } finally {
    saving.value = false;
  }
}

async function regenerateShareToken() {
  if (!appId.value) return;
  try {
    const res = await aiAppsApi.regenerateShareToken(appId.value);
    if (app.value) app.value.share_token = res.token;
    toast.success('已重新生成');
  } catch {
    toast.error('生成失败');
  }
}

async function regenerateApiToken() {
  if (!appId.value) return;
  try {
    const res = await aiAppsApi.regenerateApiToken(appId.value);
    if (app.value) app.value.api_token = res.token;
    toast.success('已重新生成');
  } catch {
    toast.error('生成失败');
  }
}

function copyShareLink() {
  if (!app.value?.share_token) return;
  const url = `${window.location.origin}/share/${app.value.share_token}`;
  navigator.clipboard.writeText(url).then(() => toast.success('已复制到剪贴板'));
}

function copyApiToken() {
  if (!app.value?.api_token) return;
  navigator.clipboard.writeText(app.value.api_token).then(() => toast.success('已复制到剪贴板'));
}

onMounted(loadApp);
</script>

<style scoped>
.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: none;
  background: transparent;
  color: var(--color-ink-secondary);
  font-size: 14px;
  cursor: pointer;
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  transition: all var(--duration-fast);
}
.back-btn:hover { background: var(--color-bg-hover); color: var(--color-ink); }

.edit-form { display: flex; flex-direction: column; gap: 24px; }

.form-section {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-ink);
  margin: 0 0 4px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-row-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.label-hint {
  font-weight: 400;
  color: var(--color-ink-tertiary);
  font-size: 12px;
}

.capability-input { display: flex; gap: 8px; }
.capability-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.cap-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  background: var(--color-accent-bg);
  color: var(--color-accent);
  font-size: 12px;
}
.cap-remove {
  border: none; background: transparent; color: inherit;
  cursor: pointer; font-size: 14px; padding: 0; line-height: 1;
}

.token-row { display: flex; gap: 8px; }
.token-row .ui-input { flex: 1; }

.field-error {
  font-size: 12px;
  color: var(--color-danger);
  margin: 4px 0 0;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 8px;
}

.loading-state { padding: 40px 0; }
</style>
