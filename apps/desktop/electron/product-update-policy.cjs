'use strict'

const PRODUCT_UPDATE_MESSAGE =
  '核心更新由 Marketing OS 团队吸收 Hermes 上游变更、完成产品回归后，通过 Marketing OS 正式版本发布。当前应用不会直接执行 hermes update。'

function productUpdateStatus(currentVersion) {
  return {
    supported: true,
    currentVersion: String(currentVersion || ''),
    updateAvailable: false,
    behind: 0,
    canApply: false,
    updateChannel: 'marketing-os-product-release',
    message: PRODUCT_UPDATE_MESSAGE,
    fetchedAt: Date.now()
  }
}

function rejectRawCoreUpdate(currentVersion) {
  return {
    ok: false,
    error: 'marketing-os-product-update-required',
    currentVersion: String(currentVersion || ''),
    updateChannel: 'marketing-os-product-release',
    message: PRODUCT_UPDATE_MESSAGE
  }
}

module.exports = { PRODUCT_UPDATE_MESSAGE, productUpdateStatus, rejectRawCoreUpdate }
