# 前端开发规范指南 (Frontend Development Guidelines)

## 1. 核心技术栈 (Tech Stack)

- **Language**: TypeScript (严格模式，禁止使用 `any`)
- **Framework**: React 18+ (Functional Components)
- **Styling**: Tailwind CSS 或 CSS Modules
- **State Management**: TanStack Query (React Query) 用于异步，Zustand 用于全局状态

## 2. 命名约定 (Naming Conventions)

- **组件文件**: 大驼峰命名 (PascalCase)。例：`UserDashboard.tsx`
- **组件函数**: 大驼峰命名。例：`export const UserCard = () => { ... }`
- **Hook 文件**: 以 `use` 开头的小驼峰。例：`useAuth.ts`
- **常量/枚举**: 全大写下划线。例：`const MAX_RETRY_LIMIT = 3;`
- **变量/普通函数**: 小驼峰命名。例：`const [isLoading, setIsLoading] = useState(false);`

## 3. 代码格式与风格 (Code Style)

- **缩进**: 2 个空格
- **引号**: JavaScript 使用单引号 `'`，JSX 属性使用双引号 `"`
- **分号**: 必须保留 `;`
- **解构**: 优先使用对象解构。例：`const { data, error } = useQuery(...)`
- **箭头函数**: 优先使用 `const` 定义的箭头函数，避免使用 `function` 关键字

## 4. 组件编写准则 (Component Principles)

- **单一职责**: 每个文件只包含一个主要组件。
- **Props 定义**: 必须使用 `interface` 或 `type` 显式定义 Props。
- **逻辑抽离**: 超过 15 行的业务逻辑或复杂的 `useEffect` 必须抽离到自定义 Hook 中。
- **渲染性能**: 使用 `useMemo` 和 `useCallback` 优化高频触发的计算和回调。

## 5. 目录结构规范 (Project Structure)

```text
frontend/
  ├── api/          # 接口定义 (与后端 Agent/Execution 对应)
  ├── components/   # 原子化/通用 UI 组件
  ├── hooks/        # 业务逻辑抽离
  ├── layouts/      # 布局组件
  ├── pages/        # 页面级组件 (路由对应)
  ├── types/        # 全局 TypeScript 类型声明
  └── utils/        # 格式化、验证等工具函数
```
