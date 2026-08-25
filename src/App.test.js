import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the application heading', () => {
  render(<App />);
  const heading = screen.getByRole('heading', {
    name: /architecture ref\. card 2/i,
  });
  expect(heading).toBeInTheDocument();
});
