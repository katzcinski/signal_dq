import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { ProductDetail, ProductListItem } from '@/types';

export const useProducts = () =>
  useQuery<ProductListItem[]>({
    queryKey: ['products'],
    queryFn: () => api.get('/products').then(r => r.data),
  });

export const useProduct = (name: string) =>
  useQuery<ProductDetail>({
    queryKey: ['products', name],
    queryFn: () => api.get(`/products/${encodeURIComponent(name)}`).then(r => r.data),
    enabled: !!name,
  });
