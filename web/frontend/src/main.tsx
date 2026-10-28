import React from 'react'
import ReactDOM from 'react-dom/client'
import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom'

import { App } from './App'
import { AuthProvider } from './lib/auth'
import { BatchDetailPage } from './pages/BatchDetailPage'
import { BatchesPage } from './pages/BatchesPage'
import { StatsPage } from './pages/StatsPage'
import { TargetsPage } from './pages/TargetsPage'
import { UsersPage } from './pages/UsersPage'
import './styles/index.css'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/batches" replace /> },
      { path: 'batches', element: <BatchesPage /> },
      { path: 'batches/:batchId', element: <BatchDetailPage /> },
      { path: 'stats', element: <StatsPage /> },
      { path: 'targets', element: <TargetsPage /> },
      { path: 'users', element: <UsersPage /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </React.StrictMode>,
)
