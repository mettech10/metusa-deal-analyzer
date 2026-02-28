'use client'

import { type Paddle, initializePaddle } from '@paddle/paddle-js'

let _paddle: Paddle | undefined

/**
 * Returns a singleton Paddle instance initialised for the correct environment.
 * Call this inside a useEffect or event handler (never at module-load time).
 */
export async function getPaddle(): Promise<Paddle | undefined> {
  if (_paddle) return _paddle

  const token = process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN
  if (!token) {
    console.warn('[Paddle] NEXT_PUBLIC_PADDLE_CLIENT_TOKEN is not set.')
    return undefined
  }

  const env = process.env.NEXT_PUBLIC_PADDLE_ENV === 'production'
    ? 'production'
    : 'sandbox'

  _paddle = await initializePaddle({
    environment: env,
    token,
    checkout: {
      settings: {
        displayMode: 'overlay',
        theme: 'dark',
        locale: 'en-GB',
        successUrl: `${typeof window !== 'undefined' ? window.location.origin : ''}/analyse?payment=success`,
      },
    },
  })

  return _paddle
}

/** Open the Paddle checkout overlay for a given price ID */
export async function openCheckout(priceId: string, email?: string) {
  const paddle = await getPaddle()
  if (!paddle) {
    console.error('[Paddle] Could not initialise Paddle — check your client token.')
    return
  }

  paddle.Checkout.open({
    items: [{ priceId, quantity: 1 }],
    customer: email ? { email } : undefined,
  })
}
