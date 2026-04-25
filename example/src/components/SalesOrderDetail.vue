<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, ShoppingCart, Calendar, User } from '@element-plus/icons-vue'

// 订单状态
const orderStatus = ref('已确认')

// 基本信息表单
const basicInfo = reactive({
  transportMethod: '',
  tradeTerms: '',
  orderSource: '',
  sourceObjectType: '',
  sourceDocumentNo: '',
  relatedOrderNo: '',
  remarks: ''
})

// 时间记录表单
const timeRecords = reactive({
  confirmTime: '',
  closeTime: '',
  orderTime: '',
  creator: '张三',
  createTime: '',
  lastModifier: '莉莉',
  lastModifyTime: ''
})

// 表格数据
const tableData = ref([
  {
    lineNo: 1,
    materialCode: 'MAT001',
    materialDesc: '机顶盒',
    materialVersion: 'V1',
    orderQuantity: 50,
    unit: '台',
    salesPrice: 100,
    status: '已发货',
    requiredDeliveryDate: '2025-07-10'
  }
])

// 表单验证规则
const basicInfoRules = {
  transportMethod: [{ required: true, message: '请选择运输方式', trigger: 'change' }],
  tradeTerms: [{ required: true, message: '请选择贸易术语', trigger: 'change' }],
  orderSource: [{ required: true, message: '请输入订单来源', trigger: 'blur' }]
}

// 运输方式选项
const transportMethods = [
  { label: '空运', value: '空运' },
  { label: '海运', value: '海运' },
  { label: '陆运', value: '陆运' }
]

// 贸易术语选项
const tradeTerms = [
  { label: 'FOB', value: 'FOB' },
  { label: 'CIF', value: 'CIF' },
  { label: 'EXW', value: 'EXW' }
]

// 新增行
const handleAddRow = () => {
  tableData.value.push({
    lineNo: tableData.value.length + 1,
    materialCode: '',
    materialDesc: '',
    materialVersion: '',
    orderQuantity: 0,
    unit: '',
    salesPrice: 0,
    status: '待处理',
    requiredDeliveryDate: ''
  })
}

// 删除行
const handleDeleteRow = (index) => {
  tableData.value.splice(index, 1)
}

// 拷贝行
const handleCopyRow = (row) => {
  const newRow = { ...row }
  newRow.lineNo = tableData.value.length + 1
  tableData.value.push(newRow)
  ElMessage.success('拷贝成功')
}

// 查看详情
const handleViewDetail = (row) => {
  ElMessage.info(`查看行 ${row.lineNo} 详情`)
}

// 提交
const handleSubmit = () => {
  ElMessageBox.confirm('确认提交订单？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    ElMessage.success('提交成功')
  }).catch(() => {})
}

// 编辑
const handleEdit = () => {
  ElMessage.info('进入编辑模式')
}

// 暂挂
const handleHold = () => {
  ElMessageBox.confirm('确认暂挂订单？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    ElMessage.success('已暂挂')
  }).catch(() => {})
}

// 取消
const handleCancel = () => {
  ElMessageBox.confirm('确认取消？未保存的数据将丢失', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '继续编辑',
    type: 'warning'
  }).then(() => {
    ElMessage.info('已取消')
  }).catch(() => {})
}
</script>

<template>
  <div class="sales-order-detail">
    <!-- 顶部卡片 - 详情概览 -->
    <el-card class="header-card" shadow="hover">
      <div class="header-content">
        <div class="header-left">
          <el-icon :size="48" color="#409EFF"><ShoppingCart /></el-icon>
          <div class="header-text">
            <h1 class="main-title">销售订单详情</h1>
            <p class="sub-title">00F0034567873QW</p>
          </div>
        </div>
        <div class="header-right">
          <el-tag :type="orderStatus === '已确认' ? 'success' : 'warning'" size="large">
            {{ orderStatus }}
          </el-tag>
        </div>
      </div>
    </el-card>

    <!-- 内容区 -->
    <div class="content-area">
      <!-- 基本信息 -->
      <el-collapse v-model="activeCollapse" accordion>
        <el-collapse-item title="基本信息" name="1">
          <el-form :model="basicInfo" :rules="basicInfoRules" label-width="120px">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="运输方式" prop="transportMethod">
                  <el-select v-model="basicInfo.transportMethod" placeholder="请选择运输方式" style="width: 100%">
                    <el-option
                      v-for="item in transportMethods"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="贸易术语" prop="tradeTerms">
                  <el-select v-model="basicInfo.tradeTerms" placeholder="请选择贸易术语" style="width: 100%">
                    <el-option
                      v-for="item in tradeTerms"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="订单来源" prop="orderSource">
                  <el-input v-model="basicInfo.orderSource" placeholder="请输入订单来源" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="来源对象类型">
                  <el-input v-model="basicInfo.sourceObjectType" placeholder="请输入来源对象类型" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="来源单据号">
                  <el-input v-model="basicInfo.sourceDocumentNo" placeholder="ABCDEFG" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="关联订单号">
                  <el-input v-model="basicInfo.relatedOrderNo" placeholder="2025080987483" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row>
              <el-col :span="24">
                <el-form-item label="备注">
                  <el-input
                    v-model="basicInfo.remarks"
                    type="textarea"
                    :rows="3"
                    placeholder="该订单为XXXXXX客户XXXXXX"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
        </el-collapse-item>

        <!-- 时间记录 -->
        <el-collapse-item title="时间记录" name="2">
          <el-form :model="timeRecords" label-width="120px">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="确认时间">
                  <el-date-picker
                    v-model="timeRecords.confirmTime"
                    type="date"
                    placeholder="选择日期"
                    style="width: 100%"
                    value-format="YYYY-MM-DD"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="关闭时间">
                  <el-date-picker
                    v-model="timeRecords.closeTime"
                    type="date"
                    placeholder="选择日期"
                    style="width: 100%"
                    value-format="YYYY-MM-DD"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="下单时间">
                  <el-date-picker
                    v-model="timeRecords.orderTime"
                    type="date"
                    placeholder="选择日期"
                    style="width: 100%"
                    value-format="YYYY-MM-DD"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="创建人">
                  <el-input v-model="timeRecords.creator" disabled>
                    <template #prefix>
                      <el-icon><User /></el-icon>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="创建时间">
                  <el-date-picker
                    v-model="timeRecords.createTime"
                    type="date"
                    placeholder="选择日期"
                    style="width: 100%"
                    value-format="YYYY-MM-DD"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="最后修改人">
                  <el-input v-model="timeRecords.lastModifier" disabled>
                    <template #prefix>
                      <el-icon><User /></el-icon>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row>
              <el-col :span="12">
                <el-form-item label="最后修改时间">
                  <el-date-picker
                    v-model="timeRecords.lastModifyTime"
                    type="date"
                    placeholder="选择日期"
                    style="width: 100%"
                    value-format="YYYY-MM-DD"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
        </el-collapse-item>

        <!-- 详细行信息 -->
        <el-collapse-item title="详细行信息" name="3">
          <div class="table-toolbar">
            <el-button type="primary" @click="handleAddRow">
              <el-icon><Document /></el-icon>
              新增
            </el-button>
          </div>
          
          <el-table :data="tableData" border style="width: 100%" stripe>
            <el-table-column type="selection" width="55" />
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="scope">
                <el-button link type="primary" size="small" @click="handleCopyRow(scope.row)">拷贝</el-button>
                <el-button link type="primary" size="small" @click="handleViewDetail(scope.row)">查看详情</el-button>
                <el-button link type="danger" size="small" @click="handleDeleteRow(scope.$index)">删除</el-button>
              </template>
            </el-table-column>
            <el-table-column label="行号" width="100">
              <template #default="scope">
                <el-input v-model="scope.row.lineNo" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="物料编码" width="150">
              <template #default="scope">
                <el-select v-model="scope.row.materialCode" placeholder="请选择" size="small" style="width: 100%">
                  <el-option label="MAT001" value="MAT001" />
                  <el-option label="MAT002" value="MAT002" />
                  <el-option label="MAT003" value="MAT003" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="物料描述" width="150">
              <template #default="scope">
                <el-input v-model="scope.row.materialDesc" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="物料版本" width="120">
              <template #default="scope">
                <el-input v-model="scope.row.materialVersion" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="订购数量" width="120">
              <template #default="scope">
                <el-input-number v-model="scope.row.orderQuantity" :min="0" size="small" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column label="单位" width="100">
              <template #default="scope">
                <el-input v-model="scope.row.unit" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="销售单价" width="120">
              <template #default="scope">
                <el-input-number v-model="scope.row.salesPrice" :min="0" :precision="2" size="small" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="scope">
                <el-tag :type="scope.row.status === '已发货' ? 'success' : 'info'">
                  {{ scope.row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="客户要求发货日期" width="180">
              <template #default="scope">
                <el-date-picker
                  v-model="scope.row.requiredDeliveryDate"
                  type="date"
                  placeholder="选择日期"
                  size="small"
                  style="width: 100%"
                  value-format="YYYY-MM-DD"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 页面底部区 -->
    <div class="footer-area">
      <el-button type="primary" @click="handleSubmit">提交</el-button>
      <el-button @click="handleEdit">编辑</el-button>
      <el-button @click="handleHold">暂挂</el-button>
      <el-button @click="handleCancel">取消</el-button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'SalesOrderDetail',
  data() {
    return {
      activeCollapse: ['1', '2', '3']
    }
  }
}
</script>

<style scoped>
.sales-order-detail {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.header-card {
  margin-bottom: 20px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-text {
  display: flex;
  flex-direction: column;
}

.main-title {
  margin: 0;
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}

.sub-title {
  margin: 8px 0 0;
  font-size: 14px;
  color: #909399;
}

.content-area {
  background: #fff;
  border-radius: 4px;
  padding: 20px;
  margin-bottom: 20px;
}

.table-toolbar {
  margin-bottom: 16px;
}

.footer-area {
  background: #fff;
  padding: 20px;
  border-radius: 4px;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.1);
}

:deep(.el-collapse-item__header) {
  font-size: 16px;
  font-weight: bold;
}

:deep(.el-form-item) {
  margin-bottom: 18px;
}
</style>
