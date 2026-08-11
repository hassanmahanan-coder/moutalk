import { test, expect } from '@playwright/test'

const API = 'http://127.0.0.1:8765'

test('发起谈判并发送首轮消息', async ({ page, request }) => {
  const email = `e2e_neg_${Math.floor(Math.random() * 1e6)}@test.com`
  const password = 'password123'
  const reg = await request.post(`${API}/api/auth/register`, {
    data: { username: `e2e_neg_${Math.floor(Math.random() * 1e6)}`, email, password },
  })
  expect(reg.ok()).toBeTruthy()

  // UI 登录
  await page.goto('/login')
  await page.getByPlaceholder(/you@example.com 或用户名/).fill(email)
  await page.getByPlaceholder('至少 8 位').fill(password)
  await page.getByRole('button', { name: '入 局' }).click()
  await expect(page.getByText('场景大厅').first().first()).toBeVisible()

  // 进入谈判室（展开谈判按钮）
  await page.getByRole('button', { name: '展开谈判' }).first().click()
  await expect(page).toHaveURL(/\/room\//)

  // 等待开场白出现
  await expect(page.locator('.bubble').first()).toBeVisible({ timeout: 15000 })

  // 发送一条消息（用户气泡立即出现；对手回复链路由后端 pytest 覆盖）
  const composer = page.locator('textarea')
  await composer.fill('报价 200 万可以吗？')
  await page.getByRole('button', { name: '出 牌' }).click()
  await expect(page.locator('.bubble-row.user .bubble').first()).toBeVisible({ timeout: 15000 })

  // 看板存在
  await expect(page.getByText('报价看板')).toBeVisible()
})
