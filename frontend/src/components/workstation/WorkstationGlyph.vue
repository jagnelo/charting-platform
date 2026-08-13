<template>
  <span class="workstation-glyph" :class="`workstation-glyph--${props.kind}`" :title="props.title" aria-hidden="true" />
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ kind: 'close' | 'chevron-down' | 'chevron-up' | 'chevron-right' | 'chevron-left' | 'reset' | 'move-left' | 'move-right' | 'move-up' | 'move-down' | 'delete' | 'pause' | 'resume' | 'repeat' | 'visible' | 'hidden' | 'duplicate' | 'copy' | 'copy-linked' | 'promote' | 'edit' | 'export' | 'plus' | 'settings' | 'warning' | 'more' | 'bell' | 'lock' | 'unlock' | 'currency' | 'approx' | 'apply' | 'list' | 'scan' ; title?: string }>(), { kind: 'close' })
</script>

<style scoped>
.workstation-glyph { display:inline-block; position:relative; width:11px; height:11px; color:currentColor; vertical-align:-1px; }
.workstation-glyph--close::before,.workstation-glyph--close::after,.workstation-glyph--delete::before,.workstation-glyph--delete::after { content:''; position:absolute; left:5px; top:0; width:1px; height:11px; background:currentColor; }
.workstation-glyph--close::before,.workstation-glyph--delete::before { transform:rotate(45deg); }
.workstation-glyph--close::after,.workstation-glyph--delete::after { transform:rotate(-45deg); }
.workstation-glyph--chevron-down::before { content:''; position:absolute; left:2px; top:3px; width:6px; height:6px; border-right:1px solid currentColor; border-bottom:1px solid currentColor; transform:rotate(45deg); }
.workstation-glyph--chevron-up::before { content:''; position:absolute; left:2px; top:5px; width:6px; height:6px; border-right:1px solid currentColor; border-bottom:1px solid currentColor; transform:rotate(225deg); }
.workstation-glyph--chevron-right::before { content:''; position:absolute; left:2px; top:2px; width:6px; height:6px; border-right:1px solid currentColor; border-bottom:1px solid currentColor; transform:rotate(-45deg); }
.workstation-glyph--chevron-left::before { content:''; position:absolute; left:3px; top:2px; width:6px; height:6px; border-left:1px solid currentColor; border-bottom:1px solid currentColor; transform:rotate(45deg); }
.workstation-glyph--reset::before { content:''; position:absolute; inset:1px; border:1px solid currentColor; border-left-color:transparent; border-radius:50%; }
.workstation-glyph--reset::after { content:''; position:absolute; right:0; top:0; border:3px solid transparent; border-right-color:currentColor; transform:rotate(-20deg); }
.workstation-glyph--move-left::before,.workstation-glyph--move-right::before,.workstation-glyph--move-up::before,.workstation-glyph--move-down::before { content:''; position:absolute; background:currentColor; }
.workstation-glyph--move-left::before,.workstation-glyph--move-right::before { left:1px; right:1px; top:5px; height:1px; }
.workstation-glyph--move-up::before,.workstation-glyph--move-down::before { top:1px; bottom:1px; left:5px; width:1px; }
.workstation-glyph--move-left::after,.workstation-glyph--move-right::after,.workstation-glyph--move-up::after,.workstation-glyph--move-down::after { content:''; position:absolute; width:5px; height:5px; border-top:1px solid currentColor; border-right:1px solid currentColor; }
.workstation-glyph--move-left::after { left:1px; top:3px; transform:rotate(-135deg); }
.workstation-glyph--move-right::after { right:1px; top:3px; transform:rotate(45deg); }
.workstation-glyph--move-up::after { left:3px; top:1px; transform:rotate(-45deg); }
.workstation-glyph--move-down::after { left:3px; bottom:1px; transform:rotate(135deg); }
.workstation-glyph--pause::before { content:''; position:absolute; left:2px; top:1px; width:2px; height:9px; background:currentColor; box-shadow:5px 0 currentColor; }
.workstation-glyph--resume::before { content:''; position:absolute; left:3px; top:1px; border:5px solid transparent; border-left:7px solid currentColor; }
.workstation-glyph--repeat::before { content:''; position:absolute; inset:1px; border:1px solid currentColor; border-left-color:transparent; border-radius:50%; }
.workstation-glyph--repeat::after { content:''; position:absolute; right:0; top:0; border:3px solid transparent; border-right-color:currentColor; }
.workstation-glyph--visible::before { content:''; position:absolute; left:1px; top:3px; width:9px; height:6px; border:1px solid currentColor; border-radius:9px / 6px; }
.workstation-glyph--visible::after { content:''; position:absolute; left:5px; top:5px; width:3px; height:3px; background:currentColor; border-radius:50%; }
.workstation-glyph--hidden::before { content:''; position:absolute; left:1px; top:3px; width:9px; height:6px; border:1px solid currentColor; border-radius:9px / 6px; opacity:.55; }
.workstation-glyph--hidden::after { content:''; position:absolute; left:1px; top:5px; width:11px; height:1px; background:currentColor; transform:rotate(35deg); }
.workstation-glyph--duplicate::before { content:''; position:absolute; left:1px; top:3px; width:6px; height:6px; border:1px solid currentColor; }
.workstation-glyph--duplicate::after { content:''; position:absolute; left:4px; top:1px; width:6px; height:6px; border:1px solid currentColor; }
.workstation-glyph--copy::before { content:''; position:absolute; left:1px; top:5px; width:8px; height:1px; background:currentColor; }
.workstation-glyph--copy::after { content:''; position:absolute; right:0; top:2px; width:6px; height:6px; border-top:1px solid currentColor; border-right:1px solid currentColor; transform:rotate(45deg); }
.workstation-glyph--copy-linked::before { content:''; position:absolute; left:0; top:5px; width:10px; height:1px; background:currentColor; }
.workstation-glyph--copy-linked::after { content:''; position:absolute; right:0; top:2px; width:6px; height:6px; border-top:1px solid currentColor; border-right:1px solid currentColor; transform:rotate(45deg); }
.workstation-glyph--promote::before { content:''; position:absolute; left:5px; top:1px; width:1px; height:9px; background:currentColor; }
.workstation-glyph--promote::after { content:''; position:absolute; left:2px; top:1px; width:6px; height:6px; border-top:1px solid currentColor; border-left:1px solid currentColor; transform:rotate(45deg); }
.workstation-glyph--edit::before { content:''; position:absolute; left:5px; top:0; width:2px; height:11px; background:currentColor; transform:rotate(45deg); }
.workstation-glyph--edit::after { content:''; position:absolute; left:2px; bottom:0; border:2px solid transparent; border-right-color:currentColor; transform:rotate(45deg); }
.workstation-glyph--export::before { content:''; position:absolute; left:5px; top:1px; width:1px; height:7px; background:currentColor; }
.workstation-glyph--export::after { content:''; position:absolute; left:2px; top:1px; width:6px; height:6px; border-top:1px solid currentColor; border-right:1px solid currentColor; transform:rotate(-45deg); }
.workstation-glyph--plus::before,.workstation-glyph--plus::after { content:''; position:absolute; left:5px; top:1px; width:1px; height:9px; background:currentColor; }
.workstation-glyph--plus::after { transform:rotate(90deg); }
.workstation-glyph--settings::before { content:''; position:absolute; inset:2px; border:1px solid currentColor; border-radius:50%; }
.workstation-glyph--settings::after { content:''; position:absolute; left:4px; top:4px; width:3px; height:3px; border:1px solid currentColor; border-radius:50%; }
.workstation-glyph--warning::before { content:''; position:absolute; left:1px; top:1px; border-left:5px solid transparent; border-right:5px solid transparent; border-bottom:9px solid currentColor; }
.workstation-glyph--warning::after { content:''; position:absolute; left:5px; top:4px; width:1px; height:3px; background:#1b252d; box-shadow:0 4px 0 -0.25px #1b252d; }
.workstation-glyph--more::before { content:''; position:absolute; left:2px; top:4px; width:3px; height:3px; border-radius:50%; background:currentColor; box-shadow:4px 0 currentColor, 8px 0 currentColor; }
.workstation-glyph--bell::before { content:''; position:absolute; left:2px; top:2px; width:7px; height:7px; border:1px solid currentColor; border-radius:5px 5px 2px 2px; }
.workstation-glyph--bell::after { content:''; position:absolute; left:1px; top:9px; width:9px; height:1px; background:currentColor; }
.workstation-glyph--lock::before { content:''; position:absolute; left:2px; top:5px; width:7px; height:6px; border:1px solid currentColor; border-radius:1px; }
.workstation-glyph--lock::after { content:''; position:absolute; left:3px; top:1px; width:5px; height:6px; border:1px solid currentColor; border-bottom:0; border-radius:5px 5px 0 0; }
.workstation-glyph--unlock::before { content:''; position:absolute; left:2px; top:5px; width:7px; height:6px; border:1px solid currentColor; border-radius:1px; }
.workstation-glyph--unlock::after { content:''; position:absolute; left:4px; top:1px; width:5px; height:6px; border:1px solid currentColor; border-bottom:0; border-left-color:transparent; border-radius:5px 5px 0 0; }
.workstation-glyph--currency::before { content:'$'; position:absolute; inset:0; font:700 10px/11px Arial, sans-serif; text-align:center; }
.workstation-glyph--approx::before { content:'≈'; position:absolute; inset:0; font:700 11px/11px Arial, sans-serif; text-align:center; }
.workstation-glyph--apply::before { content:''; position:absolute; left:5px; top:1px; width:1px; height:8px; background:currentColor; }
.workstation-glyph--apply::after { content:''; position:absolute; left:2px; top:5px; width:6px; height:6px; border-right:1px solid currentColor; border-bottom:1px solid currentColor; transform:rotate(45deg); }
.workstation-glyph--list::before { content:''; position:absolute; left:1px; top:2px; width:9px; height:1px; background:currentColor; box-shadow:0 3px currentColor,0 6px currentColor; }
.workstation-glyph--scan::before { content:''; position:absolute; left:1px; top:1px; width:8px; height:8px; border:1px solid currentColor; border-radius:50%; }
.workstation-glyph--scan::after { content:''; position:absolute; right:0; bottom:0; width:5px; height:1px; background:currentColor; transform:rotate(45deg); transform-origin:right center; }
</style>
