<template>
  <div class="page-container">
    <main class="page-content">
      <div class="card">
        <div class="docs-header">
          <h1>📖 使用文档</h1>
          <p>了解授权系统的核心概念和字段含义</p>
        </div>
        <div class="markdown-body" v-html="renderedMarkdown"></div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { marked } from 'marked'
import markdownContent from '../docs/usage.md'

const renderedMarkdown = ref('')

onMounted(() => {
  marked.setOptions({ breaks: true, gfm: true })
  renderedMarkdown.value = marked.parse(markdownContent)
})
</script>

<style scoped>
.docs-header {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 2px solid #e4e7ed;
}
.docs-header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: var(--color-text-primary);
  font-weight: 600;
}
.docs-header p {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-tertiary);
}
.markdown-body {
  font-size: 14px;
  line-height: 1.8;
  color: var(--color-text-primary);
}
.markdown-body :deep(h2) {
  margin: 32px 0 16px 0;
  padding-bottom: 8px;
  font-size: 20px;
  font-weight: 600;
  border-bottom: 1px solid #e4e7ed;
  color: var(--color-text-primary);
}
.markdown-body :deep(h3) {
  margin: 24px 0 12px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.markdown-body :deep(p) {
  margin: 12px 0;
  line-height: 1.8;
}
.markdown-body :deep(ul), .markdown-body :deep(ol) {
  margin: 12px 0;
  padding-left: 24px;
}
.markdown-body :deep(li) {
  margin: 6px 0;
}
.markdown-body :deep(code) {
  padding: 2px 6px;
  background: #f5f7fa;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  color: #e83e8c;
}
.markdown-body :deep(pre) {
  margin: 16px 0;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 6px;
  overflow-x: auto;
}
.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  color: #303133;
  font-size: 13px;
}
.markdown-body :deep(table) {
  width: 100%;
  margin: 16px 0;
  border-collapse: collapse;
  border: 1px solid #e4e7ed;
}
.markdown-body :deep(th), .markdown-body :deep(td) {
  padding: 10px 12px;
  border: 1px solid #e4e7ed;
  text-align: left;
}
.markdown-body :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
  color: var(--color-text-primary);
}
.markdown-body :deep(tr:hover) {
  background: #fafafa;
}
.markdown-body :deep(hr) {
  margin: 24px 0;
  border: none;
  border-top: 1px solid #e4e7ed;
}
.markdown-body :deep(blockquote) {
  margin: 16px 0;
  padding: 12px 16px;
  background: #f0f9ff;
  border-left: 4px solid #409eff;
  color: #606266;
}
.markdown-body :deep(strong) {
  font-weight: 600;
  color: var(--color-text-primary);
}
@media (max-width: 768px) {
  .docs-header h1 { font-size: 20px; }
  .markdown-body { font-size: 13px; }
  .markdown-body :deep(h2) { font-size: 18px; }
  .markdown-body :deep(h3) { font-size: 15px; }
  .markdown-body :deep(table) { font-size: 12px; }
  .markdown-body :deep(th), .markdown-body :deep(td) { padding: 8px; }
}
</style>
