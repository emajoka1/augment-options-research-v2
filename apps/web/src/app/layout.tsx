import './globals.css'
import type { ReactNode } from 'react'

export const metadata = {
  title: 'Augment Options Research',
  description: 'Options research platform',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
