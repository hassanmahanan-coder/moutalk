import { test, expect } from '@playwright/test'

const API = 'http://127.0.0.1:8765'
let email
let password

async function registerUser(request) {
  email = `e2e_${Math.floor(Math.random() * 1e6)}@test.com`
  password = 'password123'
  const r = await request.post(`${API}/api/auth/register`, {
    data: { username: `e2e_${Math.floor(Math.random() * 1e6)}`, email, password },
  })
  if (!r.ok()) {
    console.log('REGISTER FAIL', r.status(), await r.text())
  }
  expect(r.ok()).toBeTruthy()
}

test('用户注册到登录全流程', async ({ page, request }) => {
  await registerUser(request)
  await page.goto('/login')
  await page.getByPlaceholder(/you@example.com 或用户名/).fill(email)
  await page.getByPlaceholder('至少 8 位').fill(password)
  await page.getByRole('button', { name: '入 局' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByText('场景大厅')).toBeVisible()
})

test('登录失败提示密码错误', async ({ page, request }) => {
  await registerUser(request)
  await page.goto('/login')
  await page.getByPlaceholder(/you@example.com 或用户名/).fill(email)
  await page.getByPlaceholder('至少 8 位').fill('wrongpass')
  await page.getByRole('button', { name: '入 局' }).click()
  await expect(page.locator('.el-message')).toBeVisible()
})

test('忘记密码流程可见', async ({ page }) => {
  await page.goto('/login')
  await page.getByText('忘记密码').click()
  await expect(page.getByText('找回密码')).toBeVisible()
})
