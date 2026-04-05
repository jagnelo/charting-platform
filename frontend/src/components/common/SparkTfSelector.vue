<template>
  <select class="spark-tf-select" :value="sparkTf" @change="(e) => (sparkTf = (e.target as HTMLSelectElement).value as SparkTf)">
    <option v-for="opt in sparkTfOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
  </select>
</template>

<script setup lang="ts">
import { sparkTf, sparkTfOptions, type SparkTf } from '@/composables/useSparklines'
</script>

<style scoped>
.spark-tf-select {
  background: #111;
  border: 1px solid #222;
  color: #888;
  border-radius: 3px;
  padding: 2px 4px;
  font-size: 10px;
  font-family: inherit;
  cursor: pointer;
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  padding-right: 14px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%23555'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 4px center;
}
.spark-tf-select:hover { border-color: #444; color: #aaa; }
.spark-tf-select:focus { border-color: #64b5f6; color: #ccc; }
</style>
